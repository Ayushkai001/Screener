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

# IST fixed offset timezone: UTC+05:30 all year.
# Rationale: India does not observe Daylight Saving Time (DST). Using a fixed
# offset datetime.timezone avoids requiring third-party libraries (like pytz or zoneinfo)
# and ensures deterministic, zero-dependency behavior across all operating systems.
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
UTC = datetime.timezone.utc

# Session boundary times for Indian equity markets (NSE/BSE).
# Rationale:
#   09:00 - 09:15: Pre-open call auction where equilibrium opening price is determined.
#   09:15 - 15:30: Continuous normal market order matching and trading hours.
#   15:30 - 16:00: Post-close closing session where trades settle at official weighted close.
PRE_OPEN = datetime.time(9, 0)
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)
POST_CLOSE = datetime.time(16, 0)  # closing session ends

# NSE equity segment, weekday closures. Source: NSE circular (2026 list).
# Rationale: These dates reflect declared exchange trading holidays for the 2026 calendar year.
# On these dates, normal trading sessions do not take place despite being weekdays (Mon-Fri).
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
# Rationale: Diwali Muhurat trading occurs on Sunday evening. The exchange considers
# this a formal trading session that alters the official "previous close" for Monday.
SPECIAL_SESSIONS = {
    datetime.date(2026, 11, 8): None,   # Diwali Muhurat trading (Sunday)
}
# Rationale: Track which years have verified holiday lists to distinguish between
# a known holiday vs. dates outside the known calendar scope where we must fall back to weekday rules.
KNOWN_YEARS = {2026}


class Calendar:
    """Manages trading days, holidays, market hours, and session states for NSE/BSE.
    
    Rationale:
    Stock screeners must synchronize with exchange timing to know when to poll aggressively,
    when to idle, when to compute end-of-day metrics, and what date represents 'yesterday'
    for moving averages and percentage change calculations.
    """
    def __init__(self, holidays=None, special=None, known_years=None):
        # Rationale: Allow passing custom sets (useful for unit tests or mocking future years).
        self.holidays = set(NSE_HOLIDAYS if holidays is None else holidays)
        self.special = dict(SPECIAL_SESSIONS if special is None else special)
        self.known_years = set(KNOWN_YEARS if known_years is None else known_years)

    @classmethod
    def load(cls, path="data/holidays.json"):
        """Load optional custom holidays and special sessions from disk.
        
        Rationale:
        Enables operators to add upcoming 2027 holidays or circular-announced Muhurat hours
        dynamically without having to modify or redeploy code.
        """
        cal = cls()
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            # Rationale: Extend holidays and track additional years present in config
            for d in doc.get("holidays", []):
                day = datetime.date.fromisoformat(d)
                cal.holidays.add(day)
                cal.known_years.add(day.year)
            # Rationale: Parse custom session hours e.g. ["18:00", "19:00"] for Muhurat sessions
            for d, hrs in doc.get("special_sessions", {}).items():
                cal.special[datetime.date.fromisoformat(d)] = (
                    (datetime.time.fromisoformat(hrs[0]), datetime.time.fromisoformat(hrs[1]))
                    if hrs else None)
        return cal

    def year_known(self, d):
        """Check if date's year is covered by verified holiday data.
        
        Rationale:
        Used by the engine validation logic. If the year is unknown, missing a holiday
        is treated as non-fatal rather than corrupt data.
        """
        return d.year in self.known_years

    def is_trading_day(self, d):
        """Determine if a calendar date is an active trading session.
        
        Rationale:
        Weekends (Saturday, Sunday) are closed unless explicitly listed under special sessions
        (e.g., Sunday Muhurat or Budget session). Weekdays are open unless declared a holiday.
        """
        if d in self.special:
            return True
        return d.weekday() < 5 and d not in self.holidays

    def hours(self, d):
        """(open, close) times for a trading day, None if closed or unknown.
        
        Rationale:
        Needed by session_fraction() and market state detection to pinpoint exact opening/closing bounds.
        """
        if d in self.special:
            return self.special[d]
        if self.is_trading_day(d):
            return (OPEN, CLOSE)
        return None

    def prev_trading_day(self, d, include_special=True):
        """The session before `d` whose close is d's official previous close.
        include_special=False gives the previous *regular* session (what
        Yahoo's daily series contains).
        
        Rationale:
        On Mondays following Diwali Muhurat, the official exchange 'previous close'
        is Sunday's Muhurat close (include_special=True). However, Yahoo's daily history
        never records Muhurat trading bars, so incremental cache validation requires
        looking up the previous *regular* trading session (include_special=False).
        A 30-day lookback limit prevents infinite loops in test cases or prolonged market halts.
        """
        d -= datetime.timedelta(days=1)
        for _ in range(30):
            if self.is_trading_day(d) and (include_special or d not in self.special):
                return d
            d -= datetime.timedelta(days=1)
        raise ValueError("no trading day in the 30 days before %s" % d)

    def next_trading_day(self, d):
        """Find the next trading day following `d`.
        
        Rationale:
        Used in backtesting and forward-fill logic to determine execution dates
        for orders signaled on day t's market close.
        """
        d += datetime.timedelta(days=1)
        for _ in range(30):
            if self.is_trading_day(d):
                return d
            d -= datetime.timedelta(days=1)
        raise ValueError("no trading day in the 30 days after %s" % d)

    def last_completed_session(self, now):
        """Date of the most recent REGULAR session whose close has passed.
        
        Rationale:
        Determines what date our daily history cache MUST contain to be considered 'fresh'.
        If currently after 15:30 IST on a regular trading day, today is the completed session.
        If before 15:30 IST or on a weekend/holiday, the completed session is the previous regular day.
        Special sessions are excluded because Yahoo never provides bars for them.
        """
        local = to_ist(now)
        d = local.date()
        if d not in self.special and self.is_trading_day(d) and local.time() >= CLOSE:
            return d
        return self.prev_trading_day(d, include_special=False)

    def specials_between(self, a, b):
        """Special-session dates with a < date < b (ISO strings or dates).
        
        Rationale:
        Used by the specials patching module to find any missing Muhurat sessions
        that fall within a symbol's historical bar range.
        """
        a = datetime.date.fromisoformat(a) if isinstance(a, str) else a
        b = datetime.date.fromisoformat(b) if isinstance(b, str) else b
        return sorted(d for d in self.special if a < d < b)

    def state(self, now):
        """Market state at `now`:
        open | pre_open | post_close | closed | holiday | weekend.
        pre_open = 09:00-09:15 call auction; post_close = 15:30-16:00 closing
        session (no continuous trading, prices settle to the official close).
        
        Rationale:
        Controls the engine's polling speed and worker scheduler:
        - 'open' (09:15-15:30): Polls screen-focus symbols every 3s and full sweeps every 10s.
        - 'pre_open' / 'post_close': Moderate 60s sweeps to capture auction settlements.
        - 'closed' / 'holiday' / 'weekend': Idles at 15-minute intervals to avoid unnecessary network traffic.
        """
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
        0 before the open or on a closed day).
        
        Rationale:
        Used to calculate time-of-day adjusted relative volume (rvol_tod).
        If 50% of the trading session has elapsed, expected normal volume so far
        is 50% of 20-day average. Returns 0 before market open and 1 after market close.
        """
        local = to_ist(now)
        h = self.hours(local.date())
        if not h:
            return 0.0
        o = datetime.datetime.combine(local.date(), h[0], IST)
        c = datetime.datetime.combine(local.date(), h[1], IST)
        f = (local - o).total_seconds() / (c - o).total_seconds()
        return min(1.0, max(0.0, f))


# ---- Timezone Conversion Utilities ----
# Rationale: All network responses, timestamps, and log lines must be strictly converted
# to either UTC epoch seconds or timezone-aware IST datetimes. Naive datetimes cause subtle
# off-by-hours errors when running on servers configured to UTC or US timezones.

def now_utc():
    """Return current wall-clock time as a timezone-aware UTC datetime."""
    return datetime.datetime.now(UTC)


def to_ist(dt):
    """Convert any aware datetime to IST. Explicitly rejects naive datetimes."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime: %r (all times must be aware)" % dt)
    return dt.astimezone(IST)


def ts_to_ist(ts):
    """Convert integer epoch timestamp (seconds) to timezone-aware IST datetime."""
    return datetime.datetime.fromtimestamp(int(ts), IST)


def ts_to_date(ts):
    """Epoch seconds -> IST calendar date.
    
    Rationale:
    Yahoo stamps NSE daily bars at 09:15 IST (which is 03:45 UTC).
    Converting in UTC would produce the correct day for morning hours,
    but breaks for any bar stamped before 05:30 IST. Converting in IST
    guarantees that daily bars map to the actual exchange trading session date.
    """
    return ts_to_ist(ts).date()


def parse_now(text):
    """'2026-10-19 10:15' (IST) or ISO with offset/Z -> aware UTC datetime.
    
    Rationale:
    Supports CLI and test flags like --now '2026-10-19 10:15', automatically treating
    unspecified timezone strings as IST while accepting explicit ISO offsets.
    """
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.datetime.fromisoformat(text.replace(" ", "T", 1) if " " in text else text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)
