"""HTTP plumbing: one shared, adaptive rate limiter and polite retries.

Observed behaviour of the free endpoints this project uses (Nov 2026):
  * Yahoo answers 429 intermittently - the same request can pass, then fail a
    second later. A fixed "one retry after 5 s" (the reference repo) is not
    enough for a process that polls all day, so the limiter is AIMD:
    every 429 halves the request rate and pauses everybody for a cool-down,
    every success creeps the rate back up.
  * Yahoo's getcrumb endpoint (needed for v7/quote) is 429 for this client,
    so we rely only on spark and v8 chart, which need no cookie.
  * NSE archives need a browser-ish User-Agent; BSE's JSON API is behind
    Akamai and refuses scripts, but its bhavcopy CSV downloads fine.
"""

import gzip
import io
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
import zipfile

UA = "Mozilla/5.0"  # a Chrome-like UA got *more* 429s from Yahoo in testing


class FetchError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


class RateLimiter:
    """Token-bucket limiter shared by all threads, with AIMD adaptation.

    rate      current requests/second
    on_ok()   additive increase  (rate += step, capped at max_rate)
    on_429()  multiplicative decrease (rate /= 2, floored at min_rate), at most
              once per cool-down window, and a global pause so in-flight
              threads stop hammering together.
    """

    def __init__(self, rate=6.0, min_rate=0.5, max_rate=12.0, step=0.2, cooldown=5.0,
                 clock=time.monotonic, sleep=time.sleep):
        self.rate = rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.step = step
        self.cooldown = cooldown
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = 0.0          # earliest time the next request may start
        self._blocked_until = 0.0
        self.stats = {"ok": 0, "429": 0, "err": 0}

    def acquire(self):
        with self._lock:
            now = self._clock()
            start = max(now, self._next, self._blocked_until)
            self._next = start + 1.0 / self.rate
        wait = start - now
        if wait > 0:
            self._sleep(wait)

    def on_ok(self):
        with self._lock:
            self.stats["ok"] += 1
            self.rate = min(self.max_rate, self.rate + self.step)

    def on_429(self):
        with self._lock:
            self.stats["429"] += 1
            now = self._clock()
            # Requests already in flight when Yahoo starts throttling all come
            # back 429 together. Cut once per cool-down window, not once per
            # reply - otherwise 4 workers turn one event into a 16x slowdown.
            if now >= self._blocked_until:
                self.rate = max(self.min_rate, self.rate / 2.0)
            self._blocked_until = max(self._blocked_until,
                                      now + self.cooldown * (0.8 + 0.4 * random.random()))

    def on_error(self):
        with self._lock:
            self.stats["err"] += 1


def http_get(url, timeout=20, headers=None):
    """GET -> bytes. Transparently un-gzips. Raises FetchError(status)."""
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return body
    except urllib.error.HTTPError as e:
        raise FetchError("HTTP %s for %s" % (e.code, _short(url)), e.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise FetchError("network error for %s: %s" % (_short(url), getattr(e, "reason", e))) from None


def _short(url):
    return url if len(url) < 120 else url[:117] + "..."


class Client:
    """Rate-limited GET with retries.

    Retries: 429 -> limiter backs off, retry (up to `retries`);
             5xx / network -> retry on the alternate host if given;
             404 / 400 -> no retry (the request itself is wrong).
    """

    def __init__(self, limiter=None, retries=3, timeout=20, sleep=time.sleep):
        self.limiter = limiter or RateLimiter()
        self.retries = retries
        self.timeout = timeout
        self._sleep = sleep
        self.get_raw = http_get  # tests swap this

    def get(self, urls, headers=None):
        """urls: one URL or a list of equivalent URLs (alternate hosts)."""
        if isinstance(urls, str):
            urls = [urls]
        last = None
        for attempt in range(self.retries + 1):
            url = urls[attempt % len(urls)]
            self.limiter.acquire()
            try:
                body = self.get_raw(url, timeout=self.timeout, headers=headers)
                self.limiter.on_ok()
                return body
            except FetchError as e:
                last = e
                if e.status == 429:
                    self.limiter.on_429()
                    continue
                self.limiter.on_error()
                if e.status in (400, 401, 403, 404, 410):
                    raise
                self._sleep(min(8.0, 0.5 * 2 ** attempt) * (0.5 + random.random()))
        raise last

    def get_json(self, urls, headers=None):
        body = self.get(urls, headers)
        try:
            return json.loads(body)
        except ValueError:
            raise FetchError("not JSON (%d bytes) from %s" % (len(body), _short(
                urls if isinstance(urls, str) else urls[0]))) from None


def unzip_single(body):
    """Bytes of a .zip holding one file -> that file's bytes."""
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            if len(names) != 1:
                raise FetchError("expected one file in zip, got %r" % names)
            return z.read(names[0])
    except zipfile.BadZipFile:
        # an HTML error page served with 200 instead of the archive
        raise FetchError("not a zip archive (%d bytes)" % len(body), 404) from None


def write_atomic(path, data):
    """Write bytes/str so a crash never leaves a half-written file: write a
    temp file in the same directory, fsync, then os.replace (atomic on POSIX)."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    tmp = "%s.tmp.%d.%d" % (path, os.getpid(), threading.get_ident())
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(tmp, mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_json(path, doc, compress=None):
    if compress is None:
        compress = path.endswith(".gz")
    raw = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    write_atomic(path, gzip.compress(raw, 6) if compress else raw)


def read_json(path):
    """Read .json / .json.gz. Returns None if missing or corrupt (a corrupt
    cache must never crash the app - it is just refetched)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, EOFError):
        return None
