"""genius.mathengine — symbolic-lite math engine (no dependencies).

A real expression engine, not a wrapper:

  * tokenizer + precedence-climbing parser -> AST (Num/Var/Bin/Neg/Call/Fact)
  * evaluator with variables, constants and 25+ functions
  * rule-based symbolic differentiation (sum, product, quotient, chain, power)
  * constant-folding simplification with identity elimination
  * root finding: bisection, Newton-Raphson, secant (with step traces)
  * numerical integration: trapezoid, Simpson, adaptive Simpson
  * ODE initial-value problems: Euler and classic Runge-Kutta 4
  * Taylor-series expansion around a point (via repeated symbolic diff)
  * interpolation: Lagrange, Newton divided differences
  * percent / unit-free arithmetic helpers used by the meta-router

Everything is deterministic, stdlib-only, and JSON-serialisable. Every
solver returns its iterations so the answer carries its own evidence —
the assistant shows its work the way a careful human would.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "parse", "evaluate", "to_str", "differentiate", "simplify",
    "solve_root", "integrate", "ode_solve", "taylor", "interpolate",
    "percent_of", "expression_info", "CalcError",
]

CONSTANTS: Dict[str, float] = {
    "pi": math.pi, "e": math.e, "tau": math.tau,
    "phi": (1 + math.sqrt(5)) / 2,
}

_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "exp": math.exp, "ln": math.log, "log": math.log,
    "log2": math.log2, "log10": math.log10, "sqrt": math.sqrt,
    "abs": abs, "floor": math.floor, "ceil": math.ceil, "round": round,
    "sign": lambda x: float((x > 0) - (x < 0)),
    "gamma": math.gamma, "erf": math.erf,
    "fact": lambda x: float(math.factorial(int(x))),
    "factorial": lambda x: float(math.factorial(int(x))),
}

_MULTI_FUNCS = {
    "min": min, "max": max, "hypot": math.hypot, "atan2": math.atan2,
    "pow": pow, "gcd": math.gcd, "lcm": math.lcm,
    "ncr": lambda n, r: float(math.comb(int(n), int(r))),
    "npr": lambda n, r: float(math.perm(int(n), int(r))),
}


class CalcError(ValueError):
    """Any parse or evaluation failure, with a user-facing message."""


# ---------------------------------------------------------------------------
# 1. Tokenizer
# ---------------------------------------------------------------------------

_OPERATORS = ("+", "-", "*", "/", "^", "%", "!", "(", ")", ",", "=")
_PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "%": 2, "^": 4}  # unary minus = 3


def _tokenize(text: str) -> List[Tuple[str, Any]]:
    tokens: List[Tuple[str, Any]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            j = i
            while j < n and (text[j].isdigit() or text[j] == "."):
                j += 1
            if text[j:j + 1] == "e" and (text[j + 1:j + 2].isdigit() or text[j + 1:j + 2] in "+-"):
                k = j + 2
                while k < n and text[k].isdigit():
                    k += 1
                j = k
            tokens.append(("num", float(text[i:j])))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(("name", text[i:j]))
            i = j
            continue
        if text[i:i + 2] == "**":
            tokens.append(("op", "^"))
            i += 2
            continue
        if ch in _OPERATORS:
            tokens.append(("op", ch))
            i += 1
            continue
        raise CalcError(f"unexpected character {ch!r} at position {i}")
    tokens.append(("end", None))
    return tokens


# ---------------------------------------------------------------------------
# 2. AST + precedence-climbing parser
# ---------------------------------------------------------------------------

class _Node:
    __slots__ = ("kind", "value", "left", "right", "args", "name")

    def __init__(self, kind: str, value: Any = None, left=None, right=None,
                 args: Optional[List["_Node"]] = None, name: str = ""):
        self.kind, self.value = kind, value
        self.left, self.right = left, right
        self.args, self.name = args or [], name


def parse(text: str) -> _Node:
    """Parse an arithmetic expression into an AST. Raises CalcError."""
    tokens = _tokenize(text)
    pos = [0]

    def peek() -> Tuple[str, Any]:
        return tokens[pos[0]]

    def take() -> Tuple[str, Any]:
        tok = tokens[pos[0]]
        pos[0] += 1
        return tok

    def parse_expr(min_prec: int = 0) -> _Node:
        left = parse_atom()
        while True:
            kind, val = peek()
            if kind == "op" and val == "!" :
                take()
                left = _Node("fact", left=left)
                continue
            if kind == "op" and val in _PREC and _PREC[val] >= max(min_prec, 1):
                if _PREC[val] < min_prec:
                    break
                take()
                # right-assoc for ^, left for the rest
                next_min = _PREC[val] + (0 if val == "^" else 1)
                right = parse_expr(next_min)
                left = _Node("bin", value=val, left=left, right=right)
                continue
            break
        return left

    def parse_atom() -> _Node:
        kind, val = peek()
        if kind == "op" and val == "-":
            take()
            return _Node("neg", left=parse_expr(3))
        if kind == "op" and val == "+":
            take()
            return parse_atom()
        if kind == "num":
            take()
            return _Node("num", value=val)
        if kind == "name":
            take()
            name = str(val)
            if name in CONSTANTS and not (peek()[0] == "op" and peek()[1] == "("):
                return _Node("num", value=CONSTANTS[name], name=name)
            if peek() == ("op", "("):
                take()
                args: List[_Node] = []
                if peek() != ("op", ")"):
                    args.append(parse_expr())
                    while peek() == ("op", ","):
                        take()
                        args.append(parse_expr())
                if peek() != ("op", ")"):
                    raise CalcError(f"missing ')' after {name}(...")
                take()
                return _Node("call", name=name, args=args)
            return _Node("var", name=name)
        if kind == "op" and val == "(":
            take()
            inner = parse_expr()
            if peek() != ("op", ")"):
                raise CalcError("missing ')'")
            take()
            return inner
        raise CalcError(f"unexpected token {val!r}" if kind != "end" else "unexpected end of expression")

    tree = parse_expr()
    if peek()[0] != "end":
        raise CalcError(f"unexpected trailing token {peek()[1]!r}")
    return tree


# ---------------------------------------------------------------------------
# 3. Evaluation, printing, symbolic operations
# ---------------------------------------------------------------------------

def evaluate(node: _Node, env: Optional[Dict[str, float]] = None) -> float:
    env = env or {}
    if node.kind == "num":
        return float(node.value)
    if node.kind == "var":
        if node.name in env:
            return float(env[node.name])
        if node.name in CONSTANTS:
            return CONSTANTS[node.name]
        raise CalcError(f"unknown variable {node.name!r}")
    if node.kind == "neg":
        return -evaluate(node.left, env)
    if node.kind == "fact":
        return float(math.factorial(int(evaluate(node.left, env))))
    if node.kind == "bin":
        a = evaluate(node.left, env)
        b = evaluate(node.right, env)
        op = node.value
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                raise CalcError("division by zero")
            return a / b
        if op == "%":
            if b == 0:
                raise CalcError("modulo by zero")
            return a % b
        if op == "^":
            try:
                return a ** b
            except (OverflowError, ValueError) as exc:
                raise CalcError(f"power overflow: {exc}")
    if node.kind == "call":
        fn = _FUNCS.get(node.name) or _MULTI_FUNCS.get(node.name)
        if fn is None:
            raise CalcError(f"unknown function {node.name!r}")
        vals = [evaluate(a, env) for a in node.args]
        try:
            return float(fn(*vals))
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise CalcError(f"{node.name}({', '.join(_fmt(v) for v in vals)}): {exc}")
    raise CalcError(f"cannot evaluate node {node.kind}")


def to_str(node: _Node) -> str:
    if node.kind == "num":
        return node.name if node.name else _fmt(node.value)
    if node.kind == "var":
        return node.name
    if node.kind == "neg":
        return f"-{to_str(node.left)}"
    if node.kind == "fact":
        return f"{to_str(node.left)}!"
    if node.kind == "bin":
        return f"({to_str(node.left)} {node.value} {to_str(node.right)})"
    if node.kind == "call":
        return f"{node.name}({', '.join(to_str(a) for a in node.args)})"
    return "?"


def simplify(node: _Node) -> _Node:
    """Bottom-up constant folding + algebraic identity elimination."""
    if node.kind in ("num", "var"):
        return node
    if node.kind == "neg":
        inner = simplify(node.left)
        if inner.kind == "num":
            return _Node("num", value=-inner.value)
        if inner.kind == "neg":
            return inner.left
        return _Node("neg", left=inner)
    if node.kind == "fact":
        inner = simplify(node.left)
        if inner.kind == "num" and 0 <= inner.value == int(inner.value) and inner.value < 171:
            return _Node("num", value=float(math.factorial(int(inner.value))))
        return _Node("fact", left=inner)
    if node.kind == "call":
        args = [simplify(a) for a in node.args]
        if node.name in _FUNCS and len(args) == 1 and args[0].kind == "num":
            try:
                return _Node("num", value=float(_FUNCS[node.name](args[0].value)))
            except (ValueError, OverflowError, ZeroDivisionError):
                pass
        return _Node("call", name=node.name, args=args)
    if node.kind == "bin":
        left, right = simplify(node.left), simplify(node.right)
        op = node.value
        if left.kind == "num" and right.kind == "num":
            try:
                return _Node("num", value=evaluate(_Node("bin", value=op, left=left, right=right)))
            except CalcError:
                pass
        if op == "+":
            if _is(left, 0):
                return right
            if _is(right, 0):
                return left
        elif op == "-":
            if _is(right, 0):
                return left
            if _same(left, right):
                return _Node("num", value=0.0)
        elif op == "*":
            if _is(left, 0) or _is(right, 0):
                return _Node("num", value=0.0)
            if _is(left, 1):
                return right
            if _is(right, 1):
                return left
        elif op == "/":
            if _is(left, 0):
                return _Node("num", value=0.0)
            if _is(right, 1):
                return left
        elif op == "^":
            if _is(right, 1):
                return left
            if _is(right, 0):
                return _Node("num", value=1.0)
        return _Node("bin", value=op, left=left, right=right)
    return node


def _is(node: _Node, value: float) -> bool:
    return node.kind == "num" and abs(node.value - value) < 1e-12


def _same(a: _Node, b: _Node) -> bool:
    return to_str(a) == to_str(b)


def differentiate(node: _Node, var: str = "x") -> _Node:
    """Rule-based symbolic differentiation (sum, product, quotient, chain)."""
    if node.kind == "num":
        return _Node("num", value=0.0)
    if node.kind == "var":
        return _Node("num", value=1.0 if node.name == var else 0.0)
    if node.kind == "neg":
        return _Node("neg", left=differentiate(node.left, var))
    if node.kind == "fact":
        raise CalcError("cannot differentiate factorial expressions")
    if node.kind == "call":
        return _diff_call(node, var)
    if node.kind == "bin":
        a, b = node.left, node.right
        da, db = differentiate(a, var), differentiate(b, var)
        op = node.value
        if op == "+":
            return _Node("bin", value="+", left=da, right=db)
        if op == "-":
            return _Node("bin", value="-", left=da, right=db)
        if op == "*":  # product rule
            return _Node("bin", value="+",
                        left=_Node("bin", value="*", left=da, right=b),
                        right=_Node("bin", value="*", left=a, right=db))
        if op == "/":  # quotient rule
            num = _Node("bin", value="-",
                        left=_Node("bin", value="*", left=da, right=b),
                        right=_Node("bin", value="*", left=a, right=db))
            den = _Node("bin", value="^", left=b, right=_Node("num", value=2.0))
            return _Node("bin", value="/", left=num, right=den)
        if op == "^":
            if b.kind == "num":  # d(u^c) = c*u^(c-1)*u'
                c = b.value
                outer = _Node("bin", value="*", left=_Node("num", value=c), right=_Node(
                    "bin", value="^", left=a, right=_Node("num", value=c - 1.0)))
                return _Node("bin", value="*", left=outer, right=da)
            # general: u^v = exp(v ln u) -> (u'v/u + v' ln u) * u^v
            lnu = _Node("call", name="ln", args=[a])
            left = _Node("bin", value="/",
                         left=_Node("bin", value="*", left=da, right=b), right=a)
            right = _Node("bin", value="*", left=db, right=lnnu)
            return _Node("bin", value="*",
                         left=_Node("bin", value="+", left=left, right=right),
                         right=_Node("bin", value="^", left=a, right=b))
    raise CalcError(f"cannot differentiate node kind {node.kind}")


def _diff_call(node: _Node, var: str) -> _Node:
    arg = node.args[0]
    da = differentiate(arg, var)
    name = node.name
    chain = lambda outer: _Node("bin", value="*", left=outer, right=da)  # noqa: E731
    table = {
        "sin": lambda: chain(_Node("call", name="cos", args=[arg])),
        "cos": lambda: _Node("neg", left=chain(_Node("call", name="sin", args=[arg]))),
        "tan": lambda: chain(_Node("bin", value="^", left=_Node("call", name="sec", args=[arg]),
                                   right=_Node("num", value=2.0))),
        "exp": lambda: chain(_Node("call", name="exp", args=[arg])),
        "ln": lambda: chain(_Node("bin", value="/", left=_Node("num", value=1.0), right=arg)),
        "log": lambda: chain(_Node("bin", value="/", left=_Node("num", value=1.0), right=arg)),
        "log2": lambda: chain(_Node("bin", value="/",
                                     left=_Node("num", value=1.0),
                                     right=_Node("bin", value="*", left=_Node("num", value=math.log(2), name=None), right=arg))),
        "log10": lambda: chain(_Node("bin", value="/",
                                     left=_Node("num", value=1.0),
                                     right=_Node("bin", value="*", left=_Node("num", value=math.log(10)), right=arg))),
        "sqrt": lambda: chain(_Node("bin", value="/", left=_Node("num", value=0.5),
                                     right=_Node("call", name="sqrt", args=[arg]))),
        "sinh": lambda: chain(_Node("call", name="cosh", args=[arg])),
        "cosh": lambda: chain(_Node("call", name="sinh", args=[arg])),
        "tanh": lambda: chain(_Node("bin", value="^", left=_Node("call", name="sech", args=[arg]),
                                    right=_Node("num", value=2.0))),
        "asin": lambda: chain(_Node("bin", value="/", left=_Node("num", value=1.0),
                                     right=_Node("call", name="sqrt", args=[_Node("bin", value="-", left=_Node("num", value=1.0),
                                                                                   right=_Node("bin", value="^", left=arg, right=_Node("num", value=2.0)))]))),
        "atan": lambda: chain(_Node("bin", value="/", left=_Node("num", value=1.0),
                                     right=_Node("bin", value="+", left=_Node("num", value=1.0),
                                                  right=_Node("bin", value="^", left=arg, right=_Node("num", value=2.0))))),
    }
    if name in table:
        return table[name]()
    raise CalcError(f"cannot differentiate {name}(...)")


# ---------------------------------------------------------------------------
# 4. Solvers — each returns a dict with the answer AND its evidence
# ---------------------------------------------------------------------------

def _f(text_or_node, env: Optional[Dict[str, float]] = None):
    node = text_or_node if isinstance(text_or_node, _Node) else parse(text_or_node)

    def f(x: float) -> float:
        return evaluate(node, {**(env or {}), "x": x})

    return f, node


def solve_root(expr: str, method: str = "auto", lo: float = -100.0, hi: float = 100.0,
               x0: Optional[float] = None, tol: float = 1e-9, max_iter: int = 100) -> Dict[str, Any]:
    """Find f(x)=0 by bisection, Newton-Raphson or secant. Returns steps."""
    f, node = _f(expr)
    method = method if method != "auto" else ("newton" if x0 is not None else "bisection")
    steps: List[Dict[str, float]] = []

    if method == "bisection":
        flo, fhi = f(lo), f(hi)
        if flo * fhi > 0:
            # honest scan: try to bracket a sign change first
            found = False
            span = hi - lo
            for k in range(1, 21):
                a = lo + span * (k - 1) / 20
                b = lo + span * k / 20
                if f(a) * f(b) <= 0:
                    lo, hi, flo, fhi = a, b, f(a), f(b)
                    found = True
                    break
            if not found:
                raise CalcError("bisection: f(lo) and f(hi) have the same sign; "
                               "give a bracket --lo/--hi that contains the root")
        for i in range(max_iter):
            mid = (lo + hi) / 2
            fm = f(mid)
            steps.append({"iter": i + 1, "lo": lo, "hi": hi, "x": mid, "f": fm})
            if abs(fm) < tol or (hi - lo) / 2 < tol:
                return {"method": "bisection", "root": mid, "f_root": fm,
                        "iterations": len(steps), "steps": steps[-6:], "expr": to_str(node)}
            if flo * fm <= 0:
                hi, fhi = mid, fm
            else:
                lo, flo = mid, fm
        raise CalcError("bisection: no convergence in the iteration budget")

    if method == "newton":
        x = float(x0 if x0 is not None else 0.0)
        dnode = simplify(differentiate(node))
        d = lambda v: evaluate(dnode, {"x": v})  # noqa: E731
        for i in range(max_iter):
            fx, dx = f(x), d(x)
            steps.append({"iter": i + 1, "x": x, "f": fx, "df": dx})
            if abs(fx) < tol:
                return {"method": "newton", "root": x, "f_root": fx,
                        "iterations": len(steps), "steps": steps[-6:], "expr": to_str(node)}
            if abs(dx) < 1e-14:
                raise CalcError("newton: derivative vanished — try the secant method or another start")
            x_new = x - fx / dx
            if abs(x_new - x) < tol:
                return {"method": "newton", "root": x_new, "f_root": f(x_new),
                        "iterations": len(steps) + 1, "steps": steps[-6:], "expr": to_str(node)}
            x = x_new
        raise CalcError("newton: no convergence in the iteration budget")

    if method == "secant":
        x_prev = float(x0 if x0 is not None else 0.0)
        x = x_prev + 0.5 if x0 is None else lo
        f_prev = f(x_prev)
        for i in range(max_iter):
            fx = f(x)
            steps.append({"iter": i + 1, "x": x, "f": fx})
            if abs(fx) < tol:
                return {"method": "secant", "root": x, "f_root": fx,
                        "iterations": len(steps), "steps": steps[-6:], "expr": to_str(node)}
            if abs(fx - f_prev) < 1e-14:
                raise CalcError("secant: iterates stalled (flat line)")
            x_new = x - fx * (x - x_prev) / (fx - f_prev)
            x_prev, f_prev, x = x, fx, x_new
        raise CalcError("secant: no convergence in the iteration budget")

    raise CalcError(f"unknown method {method!r} (bisection|newton|secant)")


def integrate(expr: str, lo: float, hi: float, method: str = "simpson",
              n: int = 1000) -> Dict[str, Any]:
    """Numerical integration of f(x) over [lo, hi]."""
    if n < 2:
        raise CalcError("n must be >= 2")
    f, node = _f(expr)
    if method == "trapezoid":
        h = (hi - lo) / n
        total = (f(lo) + f(hi)) / 2 + sum(f(lo + i * h) for i in range(1, n))
        value = total * h
    elif method == "simpson":
        if n % 2:
            n += 1
        h = (hi - lo) / n
        odd = sum(f(lo + (2 * i - 1) * h) for i in range(1, n // 2 + 1))
        even = sum(f(lo + 2 * i * h) for i in range(1, n // 2))
        value = h / 3 * (f(lo) + f(hi) + 4 * odd + 2 * even)
    elif method == "adaptive":
        value = _adaptive(f, lo, hi, f(lo), f(hi), tol=1e-7)[0]
    else:
        raise CalcError(f"unknown method {method!r} (trapezoid|simpson|adaptive)")
    return {"expr": to_str(node), "method": method, "lo": lo, "hi": hi, "n": n,
            "value": value, "note": "deterministic quadrature, no sampling"}


def _adaptive(f, lo, hi, flo, fhi, tol, depth=48):
    mid = (lo + hi) / 2
    fmid = f(mid)
    whole = (hi - lo) * (flo + fhi) / 2
    left = (mid - lo) * (flo + fmid) / 2
    right = (hi - mid) * (fmid + fhi) / 2
    if depth <= 0 or abs(left + right - whole) < 15 * tol:
        return left + right + (left + right - whole) / 15, 1
    la, na = _adaptive(f, lo, mid, flo, fmid, tol / 2, depth - 1)
    ra, nb = _adaptive(f, mid, hi, fmid, fhi, tol / 2, depth - 1)
    return la + ra, na + nb + 1


def ode_solve(expr: str, x0: float, y0: float, x_end: float, h: float = 0.01,
              method: str = "rk4") -> Dict[str, Any]:
    """Solve y' = f(x, y) from (x0, y0) to x_end by RK4 or Euler."""
    node = parse(expr)
    if h <= 0 or x_end <= x0:
        raise CalcError("need h > 0 and x_end > x0")

    def f(x: float, y: float) -> float:
        return evaluate(node, {"x": x, "y": y})

    steps = max(1, int(round((x_end - x0) / h)))
    h = (x_end - x0) / steps
    x, y = x0, y0
    trace: List[Dict[str, float]] = [{"x": x, "y": y}]
    for i in range(steps):
        if method == "euler":
            y = y + h * f(x, y)
        elif method == "rk4":
            k1 = f(x, y)
            k2 = f(x + h / 2, y + h * k1 / 2)
            k3 = f(x + h / 2, y + h * k2 / 2)
            k4 = f(x + h, y + h * k3)
            y = y + h * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        else:
            raise CalcError(f"unknown method {method!r} (euler|rk4)")
        x = x0 + (i + 1) * h
        if i % max(1, steps // 200) == 0 or i == steps - 1:
            trace.append({"x": x, "y": y})
    return {"ode": to_str(node), "method": method, "x0": x0, "y0": y0,
            "x_end": x_end, "steps": steps, "y_end": y,
            "trace": trace[:200], "trace_points": len(trace)}


def taylor(expr: str, var: str = "x", around: float = 0.0, order: int = 5) -> Dict[str, Any]:
    """Taylor expansion via repeated symbolic differentiation."""
    node = parse(expr)
    terms: List[Dict[str, Any]] = []
    current = node
    for k in range(order + 1):
        val = evaluate(current, {var: around})
        if abs(val) > 1e-12:
            terms.append({"k": k, "coefficient": val / math.factorial(k)})
        if k == order:
            break
        current = simplify(differentiate(current, var))
    def _term_str(t: Dict[str, Any]) -> str:
        c = _fmt(t["coefficient"])
        if t["k"] == 0:
            return f"({c})"
        if t["k"] == 1:
            return f"({c})*{var}" if around == 0 else f"({c})*({var}-({around}))"
        if around == 0:
            return f"({c})*{var}^{t['k']}"
        return f"({c})*({var}-({around}))^{t['k']}"

    return {"expr": to_str(node), "var": var, "around": around, "order": order,
            "terms": terms,
            "series": " + ".join(_term_str(t) for t in terms) or "0"}


def interpolate(points: Sequence[Sequence[float]], x: float,
                method: str = "lagrange") -> Dict[str, Any]:
    """Interpolate f(x) through points by Lagrange or Newton divided differences."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) < 2:
        raise CalcError("need at least 2 points")
    xs = [p[0] for p in pts]
    if len(set(xs)) != len(xs):
        raise CalcError("duplicate x values in points")
    if method == "lagrange":
        total = 0.0
        for i, (xi, yi) in enumerate(pts):
            term = yi
            for j, (xj, _) in enumerate(pts):
                if i != j:
                    term *= (x - xj) / (xi - xj)
            total += term
        return {"method": "lagrange", "points": pts, "x": x, "value": total}
    if method == "newton":
        n = len(pts)
        coef = [p[1] for p in pts]
        for j in range(1, n):
            for i in range(n - 1, j - 1, -1):
                coef[i] = (coef[i] - coef[i - 1]) / (pts[i][0] - pts[i - j][0])
        # Horner evaluation over the Newton form
        value = coef[-1]
        for i in range(n - 2, -1, -1):
            value = coef[i] + (x - pts[i][0]) * value
        return {"method": "newton", "points": pts, "x": x, "value": value,
                "divided_differences": coef}
    raise CalcError(f"unknown method {method!r} (lagrange|newton)")


# ---------------------------------------------------------------------------
# 5. Small helpers used by the meta-router
# ---------------------------------------------------------------------------

def percent_of(part: float, whole: Optional[float] = None,
               reverse: bool = False) -> Dict[str, Any]:
    """percent_of(15, 80) -> 15% of 80; reverse=True -> 15 is what % of 80."""
    if reverse:
        if whole == 0:
            raise CalcError("whole is zero; percentage undefined")
        return {"part": part, "whole": whole, "percent": part / whole * 100,
                "note": f"{_fmt(part)} is {_fmt(part / whole * 100)}% of {_fmt(whole)}"}
    return {"part_percent": part, "whole": whole, "value": part / 100 * whole,
            "note": f"{_fmt(part)}% of {_fmt(whole)} = {_fmt(part / 100 * whole)}"}


def expression_info(expr: str, env: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """One-stop evaluation with the full evidence trail."""
    node = parse(expr)
    simple = simplify(node)
    value = evaluate(node, env)
    out: Dict[str, Any] = {
        "expr": expr, "canonical": to_str(simple), "value": value,
        "formatted": _fmt(value),
        "functions_used": sorted({n.name for n in _walk(node) if n.kind == "call"}),
        "variables_used": sorted({n.name for n in _walk(node) if n.kind == "var"}),
    }
    if not out["variables_used"]:
        out["simplified"] = to_str(simple) if to_str(simple) != to_str(node) else None
    return out


def _walk(node: _Node):
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        if cur.left:
            stack.append(cur.left)
        if cur.right:
            stack.append(cur.right)
        stack.extend(cur.args)


def _fmt(v: float) -> str:
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.10g}"
