"""IST clock, NSE/BSE trading calendar and market state.

Every timestamp in this project is either a UTC epoch (int seconds, what Yahoo
sends) or an aware datetime in IST. Naive datetimes are never used: the machine
running this may not be on IST, and `datetime.now()` would silently be wrong.

IST is UTC+05:30 all year (no daylight saving), so a fixed offset is exact.

The holiday list is hard-coded for the years NSE has published, and can be
extended without code changes through data/holidays.json:

    {"holidays": ["2027-01-26", ...],
     "special_sessions": {"2026-11-08": ["18:00", "19:00"]}}

A special session (Muhurat trading, a Budget-day Sunday) opens the market on a
day that is otherwise closed, at the given hours.

The calendar is a plan, not the truth: the engine also checks the data itself
(a "trading day" with no fresh ticks after the open is reported as such).
"""

import datetime
import json
import os

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
UTC = datetime.timezone.utc

PRE_OPEN = datetime.time(9, 0)
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)
POST_CLOSE = datetime.time(16, 0)  # closing session ends

# NSE equity segment, weekday closures. Source: NSE circular (2026 list).
NSE_HOLIDAYS = {
    datetime.date(2026, 1, 15),   # Municipal Corporation Election - Maharashtra
    datetime.date(2026, 1, 26),   # Republic Day
    datetime.date(2026, 3, 3),    # Holi
    datetime.date(2026, 3, 26),   # Shri Ram Navami
    datetime.date(2026, 3, 31),   # Shri Mahavir Jayanti
    datetime.date(2026, 4, 3),    # Good Friday
    datetime.date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    datetime.date(2026, 5, 1),    # Maharashtra Day
    datetime.date(2026, 5, 28),   # Bakri Id
    datetime.date(2026, 6, 26),   # Muharram
    datetime.date(2026, 9, 14),   # Ganesh Chaturthi
    datetime.date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2026, 10, 20),  # Dussehra
    datetime.date(2026, 11, 10),  # Diwali-Balipratipada
    datetime.date(2026, 11, 24),  # Guru Nanak Jayanti
    datetime.date(2026, 12, 25),  # Christmas
}
# Special sessions on otherwise-closed days. Value = (open, close) or None when
# the hours are not known here (they come by circular; add them to
# data/holidays.json). Yahoo carries NO data for these sessions - not even
# intraday - but the official close of a special session becomes the next
# day's "previous close", so history must include it (see specials.py).
SPECIAL_SESSIONS = {
    datetime.date(2026, 11, 8): None,   # Diwali Muhurat trading (Sunday)
}
KNOWN_YEARS = {2026}


class Calendar:
    def __init__(self, holidays=None, special=None, known_years=None):
        self.holidays = set(NSE_HOLIDAYS if holidays is None else holidays)
        self.special = dict(SPECIAL_SESSIONS if special is None else special)
        self.known_years = set(KNOWN_YEARS if known_years is None else known_years)

    @classmethod
    def load(cls, path="data/holidays.json"):
        cal = cls()
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            for d in doc.get("holidays", []):
                day = datetime.date.fromisoformat(d)
                cal.holidays.add(day)
                cal.known_years.add(day.year)
            for d, hrs in doc.get("special_sessions", {}).items():
                cal.special[datetime.date.fromisoformat(d)] = (
                    (datetime.time.fromisoformat(hrs[0]), datetime.time.fromisoformat(hrs[1]))
                    if hrs else None)
        return cal

    def year_known(self, d):
        return d.year in self.known_years

    def is_trading_day(self, d):
        if d in self.special:
            return True
        return d.weekday() < 5 and d not in self.holidays

    def hours(self, d):
        """(open, close) times for a trading day, None if closed or unknown."""
        if d in self.special:
            return self.special[d]
        if self.is_trading_day(d):
            return (OPEN, CLOSE)
        return None

    def prev_trading_day(self, d, include_special=True):
        """The session before `d` whose close is d's official previous close.
        include_special=False gives the previous *regular* session (what
        Yahoo's daily series contains)."""
        d -= datetime.timedelta(days=1)
        for _ in range(30):
            if self.is_trading_day(d) and (include_special or d not in self.special):
                return d
            d -= datetime.timedelta(days=1)
        raise ValueError("no trading day in the 30 days before %s" % d)

    def next_trading_day(self, d):
        d += datetime.timedelta(days=1)
        for _ in range(30):
            if self.is_trading_day(d):
                return d
            d += datetime.timedelta(days=1)
        raise ValueError("no trading day in the 30 days after %s" % d)

    def last_completed_session(self, now):
        """Date of the most recent REGULAR session whose close has passed
        (special sessions excluded: Yahoo never has a bar for them, so a cache
        could never be 'up to date' with one)."""
        local = to_ist(now)
        d = local.date()
        if d not in self.special and self.is_trading_day(d) and local.time() >= CLOSE:
            return d
        return self.prev_trading_day(d, include_special=False)

    def specials_between(self, a, b):
        """Special-session dates with a < date < b (ISO strings or dates)."""
        a = datetime.date.fromisoformat(a) if isinstance(a, str) else a
        b = datetime.date.fromisoformat(b) if isinstance(b, str) else b
        return sorted(d for d in self.special if a < d < b)

    def state(self, now):
        """Market state at `now`:
        open | pre_open | post_close | closed | holiday | weekend.
        pre_open = 09:00-09:15 call auction; post_close = 15:30-16:00 closing
        session (no continuous trading, prices settle to the official close)."""
        local = to_ist(now)
        d, t = local.date(), local.time()
        h = self.hours(d)
        if h is None and d not in self.special:
            return "weekend" if d.weekday() >= 5 else "holiday"
        if d in self.special and h is None:
            return "special"          # session today, hours unknown, no Yahoo data
        o, c = h
        if d in self.special:
            return "open" if o <= t < c else "closed"
        if o <= t < c:
            return "open"
        if PRE_OPEN <= t < o:
            return "pre_open"
        if c <= t < POST_CLOSE:
            return "post_close"
        return "closed"

    def session_fraction(self, now):
        """Fraction of today's session elapsed, 0..1 (1 after the close,
        0 before the open or on a closed day)."""
        local = to_ist(now)
        h = self.hours(local.date())
        if not h:
            return 0.0
        o = datetime.datetime.combine(local.date(), h[0], IST)
        c = datetime.datetime.combine(local.date(), h[1], IST)
        f = (local - o).total_seconds() / (c - o).total_seconds()
        return min(1.0, max(0.0, f))


def now_utc():
    return datetime.datetime.now(UTC)


def to_ist(dt):
    if dt.tzinfo is None:
        raise ValueError("naive datetime: %r (all times must be aware)" % dt)
    return dt.astimezone(IST)


def ts_to_ist(ts):
    return datetime.datetime.fromtimestamp(int(ts), IST)


def ts_to_date(ts):
    """Epoch seconds -> IST calendar date. Yahoo stamps NSE daily bars at
    09:15 IST (03:45 UTC); converting in UTC would work today but breaks for
    any bar stamped before 05:30 IST, so always convert in IST."""
    return ts_to_ist(ts).date()


def parse_now(text):
    """'2026-10-19 10:15' (IST) or ISO with offset/Z -> aware UTC datetime."""
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.datetime.fromisoformat(text.replace(" ", "T", 1) if " " in text else text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)
