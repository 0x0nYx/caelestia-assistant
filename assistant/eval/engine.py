"""The eval arena — measurement suites over the frozen system state.

Six suites, each honest about what it measures:

- ``routing``     request -> expected surface. Top-1 / top-3 / precision
                  among ROUTED / confident-wrong, with seeded bootstrap
                  intervals. Cold start: ``DEFAULT_STATE`` router weights,
                  no learned state, no session — the deterministic floor.
- ``nlplan``      request -> exact planned tool + value + validity, through
                  the real cortex pipeline (router + planner) against a
                  temp target file. Exact-match is the headline.
- ``abstention``  out-of-domain negatives must NOT be confidently routed
                  to a settings tool or preset (a coarse surface like
                  ``search``/``genius``/``explain`` is honest delegation,
                  not a settings mistake).
- ``diagnosis``   log line -> expected rule id, through the diagnostics
                  engine with the shipped rule pack.
- ``calibration`` ECE + Brier over every confident settings route the
                  routing/abstention suites produced (top-1 softmax
                  probability vs correctness). Cold-start numbers: the
                  router's confidence is NOT a calibrated posterior until
                  the learner has history; suite output says so.
- ``footprint``   in-process timing/RSS: first-route index build, steady
                  route latency p50/p95, process peak RSS. Cold-process
                  CLI latency is measured by ``scripts/measure_cli.py``
                  at the repo root — spawning processes from inside
                  ``assistant/`` is forbidden by the import policy, and
                  the arena does not get an exception.

Determinism: routing/abstention/calibration are pure functions of the
committed set files (DEFAULT_STATE, fixed bootstrap seeds). nlplan writes
only to a throwaway temp target. diagnosis reads only the shipped rules.
Latency numbers are machine-dependent by nature and are reported as
measurements, not gates; the ratchet (tests/test_eval_ratchet.py) pins the
accuracy suites only.
"""
from __future__ import annotations

import json
import math
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple

from .stats import brier, ece, proportion_ci

SET_DIR = Path(__file__).parent / "sets"

SUITES = ("routing", "nlplan", "abstention", "diagnosis", "calibration", "footprint")
SPLITS = ("dev", "sealed")

BOOT_SEED = 120


# ---------------------------------------------------------------------------
# Set loading.
# ---------------------------------------------------------------------------


def load_set(suite: str, split: str) -> Dict[str, Any]:
    path = SET_DIR / f"{suite}_{split}.json"
    if not path.exists():
        raise FileNotFoundError(f"no such set: {path.name}")
    data = json.loads(path.read_text())
    for item in data.get("items", []):
        if "id" not in item or "text" not in item:
            raise ValueError(f"malformed item in {path.name}: {item!r}")
    return data


def available(split: str) -> List[str]:
    return [s for s in SUITES if (SET_DIR / f"{s}_{split}.json").exists()]


# ---------------------------------------------------------------------------
# Timing (datetime deltas: the import policy has no `time` module; wall
# clock has microsecond resolution, which is enough for ms-scale medians).
# ---------------------------------------------------------------------------


def _now_ms() -> float:
    return datetime.now().timestamp() * 1000.0


def _median(xs: Sequence[float]) -> float:
    ys = sorted(xs)
    n = len(ys)
    if not n:
        return float("nan")
    mid = n // 2
    return ys[mid] if n % 2 else (ys[mid - 1] + ys[mid]) / 2.0


def _percentile(xs: Sequence[float], q: float) -> float:
    ys = sorted(xs)
    if not ys:
        return float("nan")
    idx = min(len(ys) - 1, max(0, int(math.floor(q * len(ys)))))
    return ys[idx]


def _peak_rss_kb() -> int:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1])
    except OSError:
        pass
    return -1


# ---------------------------------------------------------------------------
# Suite: routing (cold start — DEFAULT_STATE, pure router ranking).
# ---------------------------------------------------------------------------


def run_routing(split: str = "dev",
                state: "Any | None" = None) -> Dict[str, Any]:
    """``state`` (F28): inject a RouterState to measure ALTERNATIVE
    weights (the refit ratchet measures candidate vs current). None
    means DEFAULT_STATE — the cold-start measurement, unchanged."""
    from assistant.cortex.router import DEFAULT_STATE, Router

    data = load_set("routing", split)
    router = Router()
    results: List[Dict[str, Any]] = []
    for item in data["items"]:
        res = router.route(item["text"],
                           state=state if state is not None else DEFAULT_STATE,
                           k=5)
        cands = [(c.surface, c.kind) for c in res.candidates[:3]]
        expect_verdict = item.get("expect_verdict")
        if expect_verdict:
            # Pre-declared rule (2026-09-28 registry resync): an item whose
            # accepted tool was REMOVED upstream expects the honest
            # out-of-ontology verdict, never a confident route to a
            # coincidental tool. A confident ROUTE here counts as a
            # confident-wrong, which is exactly the signal we want.
            top1_ok = res.verdict == expect_verdict
        else:
            top1_ok = bool(cands and cands[0][0] in item["accept"])
        results.append({
            "id": item["id"], "text": item["text"],
            "verdict": res.verdict, "top3": cands,
            "top1_ok": top1_ok,
            "top3_ok": any(s in item["accept"] for s, _k in cands),
            "accept": item["accept"],
        })
    return _routing_report(split, results)


def _routing_report(split: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(results)
    top1 = [int(r["top1_ok"]) for r in results]
    top3 = [int(r["top3_ok"]) for r in results]
    routed = [r for r in results if r["verdict"] == "ROUTED"]
    routed_ok = [int(r["top1_ok"]) for r in routed] if routed else []
    wrong = [r for r in routed if not r["top1_ok"]]
    return {
        "suite": "routing", "split": split, "n": n, "routed": len(routed),
        "metrics": {
            "top1_rate": _ci(top1),
            "top3_rate": _ci(top3),
            "precision_among_routed": _ci(routed_ok) if routed_ok else ("n/a", "n/a", "n/a"),
        },
        "confident_wrong": {
            "count": len(wrong), "of_routed": len(routed),
            "rate": (round(len(wrong) / len(routed), 4) if routed else None),
            "items": [
                {"id": r["id"], "text": r["text"], "top1": r["top3"][0][0] if r["top3"] else None,
                 "accept": r["accept"]} for r in wrong],
        },
        "failures": [
            {"id": r["id"], "text": r["text"], "top1": r["top3"][0][0] if r["top3"] else None,
             "accept": r["accept"]} for r in results if not r["top1_ok"]],
    }


def _ci(outcomes: Sequence[int]) -> Tuple[float, float, float]:
    point, lo, hi = proportion_ci(list(outcomes), seed=BOOT_SEED)
    return (round(point, 4), round(lo, 4), round(hi, 4))


# ---------------------------------------------------------------------------
# Suite: nlplan (request -> exact planned tool + value, real pipeline).
# ---------------------------------------------------------------------------


def run_nlplan(split: str = "dev") -> Dict[str, Any]:
    from assistant.cortex.pipeline import process
    from assistant.cortex.router import DEFAULT_STATE

    data = load_set("nlplan", split)
    results: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="eval-nlplan-") as tmp:
        target = Path(tmp) / "shell.json"
        for item in data["items"]:
            res = process(item["text"], file_path=target, router_state=DEFAULT_STATE)
            ops = res.ops or []
            tool = ops[0]["tool"] if ops else None
            value = ops[0].get("value") if ops else None
            tool_ok = tool == item["expect_tool"]
            value_ok = _values_equal(value, item.get("expect_value"))
            valid_ok = (res.plan is None) or (not res.plan.get("errors"))
            exact = tool_ok and value_ok and valid_ok and len(ops) >= 1
            results.append({
                "id": item["id"], "text": item["text"],
                "got_tool": tool, "got_value": value,
                "expect_tool": item["expect_tool"], "expect_value": item.get("expect_value"),
                "verdict": res.verdict, "n_ops": len(ops),
                "tool_ok": bool(tool_ok), "value_ok": bool(value_ok),
                "valid_ok": bool(valid_ok), "exact": bool(exact),
            })
    exact_v = [int(r["exact"]) for r in results]
    tool_v = [int(r["tool_ok"]) for r in results]
    return {
        "suite": "nlplan", "split": split, "n": len(results),
        "metrics": {
            "exact_rate": _ci(exact_v),
            "tool_rate": _ci(tool_v),
        },
        "failures": [r for r in results if not r["exact"]],
    }


def _values_equal(got: Any, expect: Any) -> bool:
    if expect is None:
        return True  # item does not pin a value
    if isinstance(got, bool) or isinstance(expect, bool):
        return got is expect
    if isinstance(got, (int, float)) and isinstance(expect, (int, float)):
        return math.isclose(float(got), float(expect), rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(got, str) and isinstance(expect, str):
        return got.strip().lower() == expect.strip().lower()
    return got == expect


# ---------------------------------------------------------------------------
# Suite: abstention (negatives must not confidently route to settings).
# ---------------------------------------------------------------------------


def run_abstention(split: str = "dev") -> Dict[str, Any]:
    from assistant.cortex.router import DEFAULT_STATE, Router

    data = load_set("abstention", split)
    router = Router()
    results: List[Dict[str, Any]] = []
    for item in data["items"]:
        res = router.route(item["text"], state=DEFAULT_STATE, k=3)
        top = res.candidates[0] if res.candidates else None
        # A settings mistake = confident (ROUTED) route whose top-1 is a
        # settings TOOL or PRESET. A coarse surface (search/genius/explain/
        # diagnose/brain/...) is honest delegation, not a settings error.
        bad = (
            res.verdict == "ROUTED" and top is not None
            and top.kind in ("tool", "preset")
        )
        results.append({
            "id": item["id"], "text": item["text"],
            "verdict": res.verdict,
            "top1": (top.surface, top.kind) if top else None,
            "correctly_not_confident": not bad,
        })
    v = [int(r["correctly_not_confident"]) for r in results]
    return {
        "suite": "abstention", "split": split, "n": len(results),
        "metrics": {"abstain_rate": _ci(v)},
        "failures": [r for r in results if not r["correctly_not_confident"]],
    }


# ---------------------------------------------------------------------------
# Suite: diagnosis (log line -> rule id).
# ---------------------------------------------------------------------------


def run_diagnosis(split: str = "dev") -> Dict[str, Any]:
    from assistant.diagnostics.engine import diagnose, load_rules

    data = load_set("diagnosis", split)
    rules = load_rules()
    results: List[Dict[str, Any]] = []
    for item in data["items"]:
        d = diagnose(item["text"], rules=rules, top=3)
        top = d.get("top") or {}
        got = (top.get("rule") or {}).get("id")
        ok = got == item["expect_rule"]
        results.append({
            "id": item["id"], "text": item["text"],
            "got": got, "expect": item["expect_rule"], "ok": bool(ok),
            "verdict": d.get("verdict"),
        })
    v = [int(r["ok"]) for r in results]
    return {
        "suite": "diagnosis", "split": split, "n": len(results),
        "metrics": {"rule_hit_rate": _ci(v)},
        "failures": [r for r in results if not r["ok"]],
    }


# ---------------------------------------------------------------------------
# Suite: calibration (ECE + Brier over confident settings routes).
# ---------------------------------------------------------------------------


def run_calibration(split: str = "dev") -> Dict[str, Any]:
    from assistant.cortex.router import DEFAULT_STATE, Router

    routing = load_set("routing", split)
    abst = load_set("abstention", split)
    router = Router()
    probs: List[float] = []
    outcomes: List[int] = []
    for item in routing["items"]:
        res = router.route(item["text"], state=DEFAULT_STATE, k=1)
        if res.verdict == "ROUTED" and res.candidates:
            probs.append(res.candidates[0].p)
            outcomes.append(int(res.candidates[0].surface in item["accept"]))
    for item in abst["items"]:
        res = router.route(item["text"], state=DEFAULT_STATE, k=1)
        if res.verdict == "ROUTED" and res.candidates:
            top = res.candidates[0]
            if top.kind in ("tool", "preset"):
                probs.append(top.p)
                outcomes.append(0)  # a negative confidently routed is wrong
    return {
        "suite": "calibration", "split": split, "n": len(probs),
        "metrics": {
            "ece_5bin": round(ece(probs, outcomes), 4),
            "brier": round(brier(probs, outcomes), 4),
        },
        "note": ("cold-start: DEFAULT_STATE softmax probabilities, no learned "
                 "calibration history — treat as uncalibrated until the learner "
                 "has approvals (D8 labeling applies at the CLI surface)"),
        "thin": len(probs) < 30,
    }


# ---------------------------------------------------------------------------
# Suite: footprint (in-process only; see module docstring).
# ---------------------------------------------------------------------------

FOOTPRINT_BUDGETS = {
    "peak_rss_kb": 45 * 1024,
    "first_route_ms": 400.0,
    "route_p50_ms": 15.0,
    "cold_cli_ms": 250.0,   # measured by scripts/measure_cli.py, reported here
}


def run_footprint() -> Dict[str, Any]:
    from assistant.cortex.router import DEFAULT_STATE, Router

    t0 = _now_ms()
    router = Router()
    fresh_router_ms = _now_ms() - t0
    probes = [
        "make the bar taller", "turn off blur", "show seconds on the clock",
        "fewer notification popups", "put the bar at the top",
        "make the dock icons bigger", "disable the launcher",
        "more spacing between things", "use 24 hour time",
        "optimize for gaming",
    ]
    lat: List[float] = []
    for text in probes:
        t1 = _now_ms()
        router.route(text, state=DEFAULT_STATE, k=5)
        lat.append(_now_ms() - t1)
    # repeat 5x for a stabler median
    for _ in range(4):
        for text in probes:
            t1 = _now_ms()
            router.route(text, state=DEFAULT_STATE, k=5)
            lat.append(_now_ms() - t1)
    rss = _peak_rss_kb()
    return {
        "suite": "footprint", "split": "n/a",
        "metrics": {
            "fresh_router_ms": round(fresh_router_ms, 1),
            "route_p50_ms": round(_median(lat), 2),
            "route_p95_ms": round(_percentile(lat, 0.95), 2),
            "peak_rss_kb": rss,
        },
        "budgets": FOOTPRINT_BUDGETS,
        "within_budget": {
            "route_p50_ms": _median(lat) <= FOOTPRINT_BUDGETS["route_p50_ms"],
            "peak_rss_kb": rss <= FOOTPRINT_BUDGETS["peak_rss_kb"],
        },
        "note": ("in-process measurements. fresh_router_ms is a new Router() over "
                 "already-built process singletons — the true COLD first-route "
                 "and cold-CLI numbers are subprocess measurements taken by "
                 "scripts/measure_cli.py (import policy forbids subprocess inside "
                 "assistant/; no exception was requested)"),
    }


# ---------------------------------------------------------------------------
# Dispatch.
# ---------------------------------------------------------------------------


RUNNERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "routing": run_routing,
    "nlplan": run_nlplan,
    "abstention": run_abstention,
    "diagnosis": run_diagnosis,
    "calibration": run_calibration,
    "footprint": lambda **_kw: run_footprint(),
}


def run_suite(suite: str, split: str = "dev") -> Dict[str, Any]:
    if suite == "all":
        out: Dict[str, Any] = {"suites": {}}
        for name in SUITES:
            if name == "footprint" or (SET_DIR / f"{name}_{split}.json").exists():
                out["suites"][name] = RUNNERS[name](split=split)
        return out
    if suite not in RUNNERS:
        raise ValueError(f"unknown suite {suite!r} (choose from {', '.join(SUITES)})")
    return RUNNERS[suite](split=split)
