"""Screener filter language -> compiled Python closures. Never uses eval().

    rsi14 < 30 and price > sma200
    change_pct >= 2 and rvol_tod > 2 and turnover > 10cr
    exchange == "NSE" and "NIFTY50" in indices
    crosses_above(ema9, ema21) and 40 < rsi14 < 70
    industry in ["IT", "Healthcare"] or contains(name, "bank")
    double_bottom and db_score >= 60

Grammar (lowest to highest precedence):
    or  and  not  comparison (< <= > >= == != in, chainable: 30 < rsi14 < 70)
    + -   * /   unary -   atoms: number, "string", field, func(args), (expr), [list]
Numbers take Indian suffixes: 5k = 5,000   10L = 10,00,000   2cr = 2,00,00,000.

NULL semantics are three-valued, like SQL: a field with no value (not enough
history, no open yet) is None; comparisons with None are unknown; `not
unknown` is unknown; a row matches only if the whole filter is True. Without
this, `not (rsi14 > 70)` would match every stock that has no RSI at all.
"""

import math
import re

SUFFIX = {"k": 1e3, "l": 1e5, "lac": 1e5, "lakh": 1e5, "cr": 1e7, "crore": 1e7}
ALIASES = {"close": "price", "ltp": "price", "last": "price", "vol": "volume",
           "rsi": "rsi14", "atr": "atr14", "adx": "adx14", "chg": "change_pct",
           "sector": "industry", "symbol": "sym"}

TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d*)?(?:e[+-]?\d+)?|\.\d+)(?P<suf>crore|cr|lakh|lac|l|k)?(?![A-Za-z0-9_])
  | (?P<str>"[^"]*"|'[^']*')
  | (?P<op><=|>=|==|!=|<|>|\+|-|\*|/|\(|\)|\[|\]|,)
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
""", re.X | re.I)

KEYWORDS = {"and", "or", "not", "in", "true", "false", "null"}


class ExprError(ValueError):
    pass


def tokenize(src):
    out, pos = [], 0
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m:
            raise ExprError("unexpected %r at position %d" % (src[pos], pos))
        pos = m.end()
        if m.group("ws"):
            continue
        if m.group("num"):
            v = float(m.group("num")) * SUFFIX.get((m.group("suf") or "").lower(), 1)
            out.append(("num", v, m.start()))
        elif m.group("str"):
            out.append(("str", m.group("str")[1:-1], m.start()))
        elif m.group("op"):
            out.append(("op", m.group("op"), m.start()))
        else:
            w = m.group("id")
            out.append(("kw" if w.lower() in KEYWORDS else "id",
                        w.lower() if w.lower() in KEYWORDS else w, m.start()))
    out.append(("end", None, len(src)))
    return out


# ---- three-valued helpers ---------------------------------------------------

def _and(a, b):
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return bool(a) and bool(b)


def _or(a, b):
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return bool(a) or bool(b)


def _truth(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return bool(v)


def _norm(v):
    return v.lower() if isinstance(v, str) else v


def _cmp(op, a, b):
    if a is None or b is None:
        return None
    if isinstance(a, str) != isinstance(b, str):
        if op == "==":
            return False
        if op == "!=":
            return True
        return None
    a, b = _norm(a), _norm(b)
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "==":
        return a == b
    return a != b


def _in(a, b):
    if a is None or b is None:
        return None
    if isinstance(b, (list, tuple, set)):
        return _norm(a) in {_norm(x) for x in b}
    if isinstance(b, str) and isinstance(a, str):
        return a.lower() in b.lower()
    return None


def _arith(op, a, b):
    if a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return None
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if b == 0:
        return None
    return a / b


# ---- parser -----------------------------------------------------------------

class Parser:
    def __init__(self, src, fields):
        """fields: dict name -> {"type": "num"|"str"|"bool"|"list", "prev": name or None}"""
        self.src = src
        self.toks = tokenize(src)
        self.i = 0
        self.fields = fields
        self.used = set()

    def peek(self):
        return self.toks[self.i]

    def take(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, kind, val=None):
        t = self.take()
        if t[0] != kind or (val is not None and t[1] != val):
            raise ExprError("expected %s at position %d, got %r" % (
                val or kind, t[2], t[1] if t[1] is not None else "end"))
        return t

    def is_op(self, *vals):
        t = self.peek()
        return t[0] == "op" and t[1] in vals

    def is_kw(self, *vals):
        t = self.peek()
        return t[0] == "kw" and t[1] in vals

    def parse(self):
        if self.peek()[0] == "end":
            return lambda r: True
        fn = self.or_(False)
        if self.peek()[0] != "end":
            t = self.peek()
            raise ExprError("unexpected %r at position %d" % (t[1], t[2]))
        return fn

    # `prev` = evaluate identifiers as their previous-bar value (for crosses_*)
    def or_(self, prev):
        left = self.and_(prev)
        while self.is_kw("or"):
            self.take()
            right = self.and_(prev)
            left = (lambda l, r: lambda row: _or(_truth(l(row)), _truth(r(row))))(left, right)
        return left

    def and_(self, prev):
        left = self.not_(prev)
        while self.is_kw("and"):
            self.take()
            right = self.not_(prev)
            left = (lambda l, r: lambda row: _and(_truth(l(row)), _truth(r(row))))(left, right)
        return left

    def not_(self, prev):
        if self.is_kw("not"):
            self.take()
            inner = self.not_(prev)

            def fn(row):
                v = _truth(inner(row))
                return None if v is None else not v
            return fn
        return self.cmp(prev)

    def cmp(self, prev):
        left = self.sum(prev)
        parts = []
        while True:
            if self.is_op("<", "<=", ">", ">=", "==", "!="):
                op = self.take()[1]
                parts.append((op, self.sum(prev)))
            elif self.is_kw("in"):
                self.take()
                parts.append(("in", self.sum(prev)))
            elif self.is_kw("not") and self.toks[self.i + 1][:2] == ("kw", "in"):
                self.take()
                self.take()
                parts.append(("not in", self.sum(prev)))
            else:
                break
        if not parts:
            return left
        operands = [left] + [p[1] for p in parts]
        ops = [p[0] for p in parts]

        def fn(row):
            vals = [o(row) for o in operands]
            res = True
            for k, op in enumerate(ops):
                a, b = vals[k], vals[k + 1]
                if op == "in":
                    v = _in(a, b)
                elif op == "not in":
                    v = _in(a, b)
                    v = None if v is None else not v
                else:
                    v = _cmp(op, a, b)
                res = _and(res, v)
                if res is False:
                    return False
            return res
        return fn

    def sum(self, prev):
        left = self.prod(prev)
        while self.is_op("+", "-"):
            op = self.take()[1]
            right = self.prod(prev)
            left = (lambda l, r, o: lambda row: _arith(o, l(row), r(row)))(left, right, op)
        return left

    def prod(self, prev):
        left = self.unary(prev)
        while self.is_op("*", "/"):
            op = self.take()[1]
            right = self.unary(prev)
            left = (lambda l, r, o: lambda row: _arith(o, l(row), r(row)))(left, right, op)
        return left

    def unary(self, prev):
        if self.is_op("-"):
            self.take()
            inner = self.unary(prev)

            def neg(row):
                v = inner(row)
                return -v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            return neg
        return self.atom(prev)

    def atom(self, prev):
        t = self.take()
        kind, val, pos = t
        if kind == "num":
            return lambda row, v=val: v
        if kind == "str":
            return lambda row, v=val: v
        if kind == "kw" and val in ("true", "false"):
            return lambda row, v=(val == "true"): v
        if kind == "kw" and val == "null":
            return lambda row: None
        if kind == "op" and val == "(":
            inner = self.or_(prev)
            self.expect("op", ")")
            return inner
        if kind == "op" and val == "[":
            items = []
            if not self.is_op("]"):
                items.append(self.sum(prev))
                while self.is_op(","):
                    self.take()
                    items.append(self.sum(prev))
            self.expect("op", "]")
            return lambda row: [it(row) for it in items]
        if kind == "id":
            if self.is_op("("):
                return self.call(val, pos, prev)
            return self.field(val, pos, prev)
        raise ExprError("unexpected %r at position %d" % (val if val is not None else "end", pos))

    def field(self, name, pos, prev):
        key = name.lower()
        key = ALIASES.get(key, key)
        if key not in self.fields:
            close = [f for f in self.fields if f.startswith(key[:3])][:5]
            raise ExprError("unknown field %r at position %d%s" % (
                name, pos, (" (did you mean: %s?)" % ", ".join(close)) if close else ""))
        if prev:
            p = self.fields[key].get("prev")
            if not p:
                raise ExprError("field %r has no previous-day value, so it cannot be used "
                                "inside crosses_above/crosses_below" % name)
            key = p
        self.used.add(key)
        return lambda row, k=key: row.get(k)

    def call(self, name, pos, prev):
        fname = name.lower()
        self.expect("op", "(")
        start = self.i
        args = []
        if not self.is_op(")"):
            args.append(self.or_(prev))
            while self.is_op(","):
                self.take()
                args.append(self.or_(prev))
        self.expect("op", ")")
        if fname in ("crosses_above", "crosses_below"):
            if len(args) != 2:
                raise ExprError("%s takes 2 arguments" % fname)
            # re-parse the same tokens in prev mode for yesterday's values
            end = self.i
            self.i = start
            pargs = [self.or_(True)]
            while self.is_op(","):
                self.take()
                pargs.append(self.or_(True))
            self.i = end
            a, b = args
            pa, pb = pargs
            up = fname == "crosses_above"

            def fn(row):
                now = _cmp(">" if up else "<", a(row), b(row))
                was = _cmp("<=" if up else ">=", pa(row), pb(row))
                return _and(now, was)
            return fn
        if fname == "abs":
            if len(args) != 1:
                raise ExprError("abs takes 1 argument")
            f0 = args[0]
            return lambda row: (abs(f0(row)) if isinstance(f0(row), (int, float)) else None)
        if fname in ("min", "max"):
            if not args:
                raise ExprError("%s needs arguments" % fname)
            agg = min if fname == "min" else max

            def fn(row):
                vals = [g(row) for g in args]
                if any(v is None or isinstance(v, str) for v in vals):
                    return None
                return agg(vals)
            return fn
        if fname == "contains":
            if len(args) != 2:
                raise ExprError("contains takes 2 arguments")
            a, b = args
            return lambda row: _in(b(row), a(row))
        if fname == "pct":     # pct(a, b) = (a/b - 1) * 100
            if len(args) != 2:
                raise ExprError("pct takes 2 arguments")
            a, b = args

            def fn(row):
                x, y = a(row), b(row)
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or y == 0:
                    return None
                return (x / y - 1) * 100
            return fn
        raise ExprError("unknown function %r at position %d" % (name, pos))


def compile_filter(src, fields):
    """-> (predicate(row) -> bool, set of fields used). Raises ExprError."""
    if len(src) > 2000:
        raise ExprError("filter too long")
    p = Parser(src, fields)
    fn = p.parse()
    return (lambda row: fn(row) is True), p.used


def compile_value(src, fields):
    """-> (value(row) -> float | None, set of fields used). For price levels
    such as a stop "low - 0.5 * atr14" or a target "db_target". Anything that
    is not a finite number (a missing field, a boolean) evaluates to None."""
    if len(src) > 2000:
        raise ExprError("expression too long")
    p = Parser(src, fields)
    if p.peek()[0] == "end":
        raise ExprError("empty expression")
    fn = p.parse()

    def value(row):
        v = fn(row)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        return float(v) if math.isfinite(v) else None
    return value, p.used
