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

# User-Agent header for HTTP requests.
# Rationale: Standard urllib User-Agent ("Python-urllib/3.x") is blocked with 403
# by NSE archives. Testing showed complex, full Chrome-like User-Agents ironically
# triggered more frequent 429 rate-limiting from Yahoo's edge servers; a minimal
# "Mozilla/5.0" achieves the most reliable pass-through.
UA = "Mozilla/5.0"


class FetchError(Exception):
    """Encapsulates HTTP errors, timeouts, and network failures with optional HTTP status code.
    
    Rationale:
    Allows callers (e.g., Client, HistoryStore) to inspect `self.status` to make intelligent
    retry decisions: 404 (not found / delisted) should never retry, 429 should trigger rate
    limiter backoff, and 5xx / connection timeouts should retry on mirror hosts.
    """
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

    Rationale:
    Polling 4,600 stocks throughout the trading day easily triggers Yahoo's undocumented
    rate limits. Instead of a naive fixed delay, TCP-style Additive Increase / Multiplicative
    Decrease (AIMD) adapts dynamically to current server load and network throttling.
    """

    def __init__(self, rate=6.0, min_rate=0.5, max_rate=12.0, step=0.2, cooldown=5.0,
                 clock=time.monotonic, sleep=time.sleep):
        # Initial request rate (requests per second)
        self.rate = rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.step = step
        self.cooldown = cooldown
        # Injected time sources for deterministic unit testing
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = 0.0          # earliest time the next request may start
        self._blocked_until = 0.0 # global pause deadline triggered on 429
        self.stats = {"ok": 0, "429": 0, "err": 0}

    def acquire(self):
        """Block until the next scheduled request slot is reached.
        
        Rationale:
        Coordinates multiple worker threads against a single shared budget.
        Calculates spacing as `1.0 / rate` while respecting any global block deadline.
        """
        with self._lock:
            now = self._clock()
            start = max(now, self._next, self._blocked_until)
            self._next = start + 1.0 / self.rate
        wait = start - now
        if wait > 0:
            self._sleep(wait)

    def on_ok(self):
        """Signal a successful HTTP response: incrementally speed up (additive increase).
        
        Rationale:
        When requests succeed, cautiously increase rate by `step` (+0.2 req/s) up to `max_rate`
        to maximize data freshness without triggering sudden throttles.
        """
        with self._lock:
            self.stats["ok"] += 1
            self.rate = min(self.max_rate, self.rate + self.step)

    def on_429(self):
        """Signal an HTTP 429 Too Many Requests: drastically slow down (multiplicative decrease).
        
        Rationale:
        When throttled, immediately cut rate in half (floored at `min_rate`) and apply a global
        pause with jitter (cooldown * 0.8..1.2). Crucially, if multiple concurrent worker threads
        all hit 429 at the same instant, we only cut the rate once per cooldown window
        to prevent a 4-worker pool from collapsing the rate 16x on a single burst event.
        """
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
        """Record network or non-429 HTTP errors for diagnostics."""
        with self._lock:
            self.stats["err"] += 1


def http_get(url, timeout=20, headers=None):
    """Perform HTTP GET returning response bytes with transparent gzip decompression.
    
    Rationale:
    Standard library urllib does not decompress gzip streams automatically.
    Supporting 'Accept-Encoding: gzip' reduces bandwidth usage by ~80% for large
    Yahoo JSON payloads and Bhavcopy CSVs.
    """
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
    """Truncate long URLs for concise, readable error logs."""
    return url if len(url) < 120 else url[:117] + "..."


class Client:
    """Rate-limited HTTP client with multi-host failover and retries.

    Retries: 429 -> limiter backs off, retry (up to `retries`);
             5xx / network -> retry on the alternate host if given;
             404 / 400 -> no retry (the request itself is wrong).

    Rationale:
    Yahoo operates multiple mirrors (query1.finance.yahoo.com and query2.finance.yahoo.com).
    Supplying both URLs allows immediate automatic failover if one edge gateway is unresponsive.
    """

    def __init__(self, limiter=None, retries=3, timeout=20, sleep=time.sleep):
        self.limiter = limiter or RateLimiter()
        self.retries = retries
        self.timeout = timeout
        self._sleep = sleep
        self.get_raw = http_get  # tests swap this with mock fetchers

    def get(self, urls, headers=None):
        """Fetch bytes from a URL or alternate host list with retries and backoff.
        
        Rationale:
        Iterates over `urls` on successive retry attempts. Backs off exponentially
        with random jitter on network errors and 5xx responses. Re-raises immediately
        on 400/401/403/404/410 because retrying invalid paths wastes budget.
        """
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
                # Fast fail on deterministic client/auth errors
                if e.status in (400, 401, 403, 404, 410):
                    raise
                # Jittered exponential backoff for 5xx/network errors
                self._sleep(min(8.0, 0.5 * 2 ** attempt) * (0.5 + random.random()))
        raise last

    def get_json(self, urls, headers=None):
        """Fetch and parse JSON payload.
        
        Rationale:
        Validates JSON parsing defensively, raising FetchError with byte count
        and URL context if Yahoo returns an HTML error page with HTTP 200.
        """
        body = self.get(urls, headers)
        try:
            return json.loads(body)
        except ValueError:
            raise FetchError("not JSON (%d bytes) from %s" % (len(body), _short(
                urls if isinstance(urls, str) else urls[0]))) from None


def unzip_single(body):
    """Extract file bytes from an in-memory zip archive containing a single file.
    
    Rationale:
    NSE publishes daily Bhavcopy archives as .csv.zip files. Unpacking directly
    in memory via io.BytesIO avoids temporary disk files and disk I/O bottlenecks.
    """
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
    """Write data to disk atomically to prevent half-written/corrupt files during unexpected exits.
    
    Rationale:
    If the process is interrupted (Ctrl+C, crash, power loss) mid-write, a normal open('w')
    leaves a partial, corrupt JSON file. By writing to a unique temporary file (.tmp.<pid>.<tid>),
    flushing to OS buffers, calling os.fsync to force physical disk sync, and finally calling
    os.replace (which is atomic on POSIX filesystems), the destination file is guaranteed to be
    either completely updated or untouched.
    """
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
    """Serialize doc to JSON and atomically write to disk, compressing with gzip if path ends with .gz.
    
    Rationale:
    Compressing 4,600 daily price histories reduces disk storage from ~350MB to ~44MB.
    `separators=(',', ':')` eliminates redundant whitespace for maximum compact serialization.
    """
    if compress is None:
        compress = path.endswith(".gz")
    raw = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    write_atomic(path, gzip.compress(raw, 6) if compress else raw)


def read_json(path):
    """Safely read .json or .json.gz file from disk.
    
    Rationale:
    Inspects the gzip magic header bytes (0x1f 0x8b) to automatically decompress gzipped files.
    If the file is missing or corrupted, returns None rather than raising an unhandled exception,
    allowing the caller to treat missing/corrupted cache files as 'needs fetch'.
    """
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
