"""HTTP + Server-Sent Events. Standard library only.

GET /                   the screener UI
GET /api/meta           fields, presets, default columns
GET /api/status         engine status
GET /api/screen?...     one-shot result (JSON)
GET /api/stream?...     live results (SSE): a new table whenever data changes,
                        at most once per `min_push` seconds
GET /api/symbol?ysym=   one row + recent daily bars (detail panel)
GET /backtest           the backtest UI
POST /api/backtest      start a backtest (JSON spec) -> {"id"}; one at a time
GET /api/backtest?id=   progress of a running job, or a saved result
GET /api/backtests      saved runs, newest first
GET /api/backtest.csv?id=   trade list as CSV

Query: filter=<expr>&sort=<field>&desc=1&limit=200&cols=a,b,c

Notes:
  * Binds 127.0.0.1 by default - the screener is not meant to be exposed.
  * JSON never contains NaN/Infinity (invalid JSON that breaks JSON.parse):
    non-finite floats become null.
  * SSE pushes the whole (limited) table each time instead of diffs: a
    dropped event can never leave the browser out of sync. The browser
    diffs to flash changed cells.
  * Client disconnects surface as BrokenPipe/ConnectionReset on write; the
    handler thread just ends.
"""

import functools
import json
import math
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import io
import traceback

from . import backtest, expr
from .fields import DEFAULT_COLUMNS, FIELDS, PRESETS

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
ALWAYS = ["ysym", "sym", "exchange", "age", "hist_ok", "note"]
MAX_LIMIT = 2000


def deep_clean(v):
    """clean() through dicts/lists: backtest results must never put NaN or
    Infinity on the wire (json.dumps(allow_nan=False) would raise)."""
    if isinstance(v, dict):
        return {k: deep_clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [deep_clean(x) for x in v]
    return clean(v)


MAX_TRADES_SENT = 3000


class Jobs:
    """Backtests run one at a time in a background thread (each one uses a
    process pool across the CPU cores). Finished results are saved to
    results/backtests and served from there."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = {}
        self.running = None

    def start(self, spec, universe_doc):
        backtest.prepare(spec)                       # raises with a user-facing message
        with self.lock:
            if self.running:
                raise RuntimeError("a backtest is already running")
            jid = "job%d" % int(time.time() * 1000)
            self.jobs[jid] = {"state": "running", "progress": 0.0, "started": time.time()}
            self.running = jid
        threading.Thread(target=self._run, args=(jid, spec, universe_doc), daemon=True).start()
        return jid

    def _run(self, jid, spec, universe_doc):
        job = self.jobs[jid]
        try:
            workers = max(1, (os.cpu_count() or 2) - 2)    # leave the live screener a core or two
            res = backtest.run(spec, universe_doc, workers=workers,
                               progress=lambda x: job.__setitem__("progress", x))
            backtest.save_result(res)
            job.update(state="done", progress=1.0, result_id=res["id"])
        except Exception as e:   # surface the reason; never kill the server
            job.update(state="error", error=str(e) or type(e).__name__, trace=traceback.format_exc()[-2000:])
        finally:
            with self.lock:
                self.running = None

    def get(self, jid):
        return self.jobs.get(jid)


def result_for_wire(res):
    """A saved result without the heavy parts the page does not need at once."""
    out = dict(res)
    for k in ("trades", "taken"):
        rows = res.get(k) or []
        out[k + "_total"] = len(rows)
        out[k] = rows[-MAX_TRADES_SENT:]
    return deep_clean(out)


def clean(v):
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return round(v, 4) if abs(v) < 1e6 else round(v, 1)
    return v


@functools.lru_cache(maxsize=256)
def _compile(src):
    return expr.compile_filter(src, FIELDS)


def _sort_key(field, desc):
    def key(r):
        v = r.get(field)
        if v is None:
            return (1, 0)                    # None last in both directions
        if isinstance(v, str):
            v = v.lower()
            return (0, v) if not desc else (0, _Rev(v))
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, (list, tuple)):
            return (1, 0)
        return (0, -v if desc else v)
    return key


@functools.total_ordering
class _Rev:
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v

    def __eq__(self, o):
        return self.v == o.v

    def __lt__(self, o):
        return self.v > o.v


def screen(engine, params):
    """params: dict of query values -> result dict. Raises expr.ExprError."""
    src = (params.get("filter") or "").strip()
    pred, _ = _compile(src)
    sort = params.get("sort") or "turnover"
    if sort not in FIELDS and sort not in ("age",):
        raise expr.ExprError("unknown sort field %r" % sort)
    desc = params.get("desc", "1") not in ("0", "false", "")
    try:
        limit = max(1, min(MAX_LIMIT, int(params.get("limit") or 200)))
    except ValueError:
        limit = 200
    cols = [c for c in (params.get("cols") or "").split(",") if c in FIELDS] or list(DEFAULT_COLUMNS)
    want = list(dict.fromkeys(ALWAYS + cols))

    rows = engine.snapshot()
    matched = [r for r in rows if pred(r)]
    matched.sort(key=_sort_key(sort, desc))
    top = matched[:limit]
    return {
        "columns": want,
        "rows": [[clean(r.get(c)) for c in want] for r in top],
        "matched": len(matched),
        "total": len(rows),
        "version": engine.version,
        "status": engine.status(),
        "ysyms": [r["ysym"] for r in top],
    }


class Handler(BaseHTTPRequestHandler):
    engine = None
    jobs = Jobs()
    min_push = 1.0
    server_version = "nse-screener/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):   # quiet: the terminal is for the engine
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, separators=(",", ":"), allow_nan=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        params = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(WEB, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if u.path in ("/backtest", "/backtest.html"):
                with open(os.path.join(WEB, "backtest.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if u.path == "/api/backtests":
                return self._send(200, {"runs": deep_clean(backtest.list_results()),
                                        "running": self.jobs.running,
                                        "defaults": deep_clean({k: v for k, v in backtest.DEFAULTS.items()})})
            if u.path == "/api/backtest":
                return self._bt_get(params.get("id", ""))
            if u.path == "/api/backtest.csv":
                return self._bt_csv(params.get("id", ""))
            if u.path == "/api/meta":
                return self._send(200, {"fields": FIELDS, "presets": PRESETS, "default_columns": DEFAULT_COLUMNS})
            if u.path == "/api/status":
                return self._send(200, self.engine.status())
            if u.path == "/api/screen":
                return self._send(200, screen(self.engine, params))
            if u.path == "/api/stream":
                return self._stream(params)
            if u.path == "/api/symbol":
                return self._symbol(params.get("ysym", ""))
            return self._send(404, {"error": "not found"})
        except expr.ExprError as e:
            return self._send(400, {"error": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path != "/api/backtest":
            return self._send(404, {"error": "not found"})
        # JSON only: a cross-site form post cannot send application/json
        # without a CORS preflight, which this server never approves
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._send(415, {"error": "send application/json"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 65536:
            return self._send(413, {"error": "bad body size"})
        try:
            spec = json.loads(self.rfile.read(n))
            if not isinstance(spec, dict):
                raise ValueError("spec must be a JSON object")
        except ValueError as e:
            return self._send(400, {"error": "bad JSON: %s" % e})
        uni = {"symbols": sorted(self.engine.info.values(), key=lambda x: -x.get("turnover", 0))}
        try:
            jid = self.jobs.start(spec, uni)
        except RuntimeError as e:
            return self._send(409, {"error": str(e)})
        except ValueError as e:                      # SpecError / ExprError
            return self._send(400, {"error": str(e)})
        return self._send(202, {"id": jid})

    def _bt_get(self, rid):
        job = self.jobs.get(rid)
        if job is not None:
            body = {k: v for k, v in job.items() if k != "trace"}
            if job["state"] == "done":
                res = backtest.load_result(job["result_id"])
                body["result"] = result_for_wire(res) if res else None
            return self._send(200, body)
        res = backtest.load_result(rid)
        if res is None:
            return self._send(404, {"error": "no such backtest"})
        return self._send(200, {"state": "done", "progress": 1.0, "result_id": rid, "result": result_for_wire(res)})

    def _bt_csv(self, rid):
        job = self.jobs.get(rid)
        res = backtest.load_result(job.get("result_id") if job else rid)
        if res is None:
            return self._send(404, {"error": "no such backtest"})
        buf = io.StringIO()
        backtest.write_csv_to(res["trades"], buf)
        return self._send(200, buf.getvalue(), "text/csv; charset=utf-8",
                          {"Content-Disposition": 'attachment; filename="%s.csv"' % res.get("id", "backtest")})

    def _symbol(self, ysym):
        eng = self.engine
        row = next((r for r in eng.snapshot() if r["ysym"] == ysym), None)
        if row is None:
            return self._send(404, {"error": "unknown symbol %r" % ysym})
        bars = [list(b) for b in eng.history.bars(ysym)[-130:]]
        return self._send(200, {"row": {k: clean(v) for k, v in row.items()}, "bars": bars})

    def _stream(self, params):
        try:
            screen(self.engine, params)                    # validate before switching to SSE
        except expr.ExprError as e:
            return self._send(400, {"error": str(e)})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        eng = self.engine
        version, last_push = -1, 0.0
        try:
            while not getattr(self.server, "stopping", False):
                v = eng.wait_change(version, timeout=15.0)
                now = time.monotonic()
                if v == version and now - last_push < 15.0:
                    continue
                wait = self.min_push - (now - last_push)
                if wait > 0:
                    time.sleep(wait)
                    v = eng.version
                res = screen(eng, params)
                eng.set_focus(res["ysyms"][:200])
                data = json.dumps(res, separators=(",", ":"), allow_nan=False)
                self.wfile.write(("event: table\ndata: %s\n\n" % data).encode())
                self.wfile.flush()
                version, last_push = v, time.monotonic()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return


def serve(engine, host="127.0.0.1", port=8765, log=print):
    Handler.engine = engine
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.stopping = False
    log("Screener UI: http://%s:%d/" % (host, port))
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log("stopping")
    finally:
        httpd.stopping = True
        engine.stop()
        httpd.server_close()
