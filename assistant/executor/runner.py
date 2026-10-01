"""executor.runner — the tiny process runner.

Runs typed ActionPlans. Contract:
- argv TUPLES only (a str argv cannot reach here; Step rejects it);
- never shell=True;
- every run is timeout-bounded;
- honest result dicts, never exceptions across the boundary;
- if a postcondition probe fails after a mutating plan, the runner
  executes the plan's revert and SAYS SO in the result.

The runner is the one place in assistant/ that imports subprocess
(together with the dbus surface, pending its executor migration).
"""
from __future__ import annotations

import subprocess
from typing import Any, Dict

from .plan import ActionPlan, Step

__all__ = ["run", "run_step"]

_RUNNER = {"subprocess": subprocess}  # patchable point for tests


def run_step(step: Step) -> Dict[str, Any]:
    """Run one step. Returns an honest dict; never raises across the
    boundary (timeouts and missing binaries are results, not crashes)."""
    try:
        completed = _RUNNER["subprocess"].run(
            list(step.argv), capture_output=True, text=True,
            timeout=step.timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return {"argv": list(step.argv), "ok": False,
                "error": f"timeout after {step.timeout_s}s"}
    except OSError as exc:
        return {"argv": list(step.argv), "ok": False,
                "error": f"{type(exc).__name__}: {exc}"}
    return {
        "argv": list(step.argv),
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run(plan: ActionPlan) -> Dict[str, Any]:
    """Run an ActionPlan: steps in order; on failure stop and report;
    on postcondition failure after a mutating plan, run the revert and
    mark the result reverted=True. Read-only plans never auto-revert
    (there is nothing to revert)."""
    results = []
    for step in plan.steps:
        res = run_step(step)
        results.append(res)
        if not res["ok"]:
            return {
                "plan": plan.description or "<unnamed>",
                "ok": False, "reverted": False,
                "stopped_at": list(step.argv),
                "steps": results,
            }
    post_ok = True
    if plan.postcondition_argv is not None:
        probe = run_step(Step(plan.postcondition_argv))
        post_ok = probe["ok"]
        results.append({"postcondition": probe})
    if post_ok:
        return {"plan": plan.description or "<unnamed>", "ok": True,
                "reverted": False, "steps": results}
    # postcondition failed: auto-revert mutating plans
    if plan.revert is not None:
        rev = run(plan.revert)
        return {"plan": plan.description or "<unnamed>", "ok": False,
                "reverted": bool(rev.get("ok")),
                "steps": results, "revert": rev}
    if plan.on_postcondition_fail is not None:
        plan.on_postcondition_fail({"plan": plan.description,
                                    "steps": results})
    return {"plan": plan.description or "<unnamed>", "ok": False,
            "reverted": False, "steps": results}
