"""JSON bridge: one request object in, one response object out.

For a QML Process (or any local caller) to drive the brain without parsing text:

    echo '{"op": "forecast", "series": [3, 4, 5]}' | caelestia-assist api

Response: {"ok": true, "op": ..., "result": ...} or {"ok": false, "op": ..., "error": ...}.
Every op returns plain data; proposals are only ever created, never applied.

Scope note (issue #120 split): the personal-knowledge-management ops
(organize, tag, plan, estimate_*, review_*, remind_*, cull, ledger_learn,
links_suggest, note_keywords, note_summarize, spellcheck, ghosts, journal_*,
health_report) moved to assistant/brain/personal/ and are NOT exposed here —
the bridge is shell-native surface only.
"""
import argparse
import json
import sys

from . import service
from . import state as st
from .cli import DEFAULT_LEDGER


OPS = {
    "forecast": lambda q, s, l: service.forecast(q["series"], horizon=int(q.get("horizon", 7))),
    "focus": lambda q, s, l: service.focus(list(q["labels"])),
    "ledger_list": lambda q, s, l: service.ledger_list(l),
    "ledger_decide": lambda q, s, l: service.ledger_decide(q["id"], q["approve"], l),
    "rhythm_report": lambda q, s, l: service.rhythm_report(q.get("weekdays", []),
                                                           q.get("hours", []),
                                                           threshold=float(q.get("threshold", 1.5))),
    "placement_propose": lambda q, s, l: service.placement_propose(
        q["text"], q["registry"], l, propose=bool(q.get("propose")), top=int(q.get("top", 5))),
    "calibration_report": lambda q, s, l: service.calibration_report(l, bins=int(q.get("bins", 5))),
    "budget_choose": lambda q, s, l: service.budget_choose(s),
    "budget_feedback": lambda q, s, l: service.budget_feedback(q["arm"], q["engaged"], s),
    "drift_check": lambda q, s, l: service.drift_check(
        q["old"], q["new"], l, propose=bool(q.get("propose")),
        similarity_threshold=float(q.get("similarity_threshold", 0.85))),
    "dream_window": lambda q, s, l: service.dream_window(
        q["idle_minutes"], q["on_ac_power"], q["cpu_load_percent"], q["jobs"], q["budget_min"]),
    # ---- issue #120 phase 2 ops (workspace profiles / topology / settings rhythm) ----
    "workspace_profiles": lambda q, s, l: service.workspace_profiles(
        q["records"], l, propose=bool(q.get("propose")),
        k=q.get("k"), min_support=int(q.get("min_support", 3)),
        purity=float(q.get("purity", 0.6))),
    "topology_observe": lambda q, s, l: service.topology_observe(
        q["file"], s, l, propose=bool(q.get("propose"))),
    "settings_rhythm": lambda q, s, l: service.settings_rhythm(
        q["file"], scheme_switches=q.get("scheme_switches"), ledger_path=l),
    "telemetry_snapshot": lambda q, s, l: _telemetry_snapshot(q),
    # ---- cortex ops (learned intelligence layer; routing is read-only) ----
    "route": lambda q, s, l: _cortex_route(q, s),
    "chat_turn": lambda q, s, l: _cortex_chat_turn(q, s),
    "dispatch": lambda q, s, l: _cortex_dispatch(q, s),
    "gap_report": lambda q, s, l: _cortex_gap_report(s),
    "gap_propose": lambda q, s, l: _cortex_gap_propose(s, l),
    "cortex_report": lambda q, s, l: _cortex_report(s),
    "memory_recall": lambda q, s, l: _cortex_memory_recall(q, s),
    "learn_feedback": lambda q, s, l: _cortex_learn_feedback(q, s),
    # ---- genius ops (universal intelligence layer; read-only analysis) ----
    "genius_do": lambda q, s, l: _genius_do(q, s),
    "genius_learn": lambda q, s, l: _genius_learn(q, s),
    "genius_report": lambda q, s, l: _genius_report(s, l),
    "genius_math": lambda q, s, l: _genius_safe(q, "mathengine.expression_info", q["expr"]),
    "genius_stats": lambda q, s, l: _genius_safe(q, "stats.describe", q["numbers"]),
    "genius_logic": lambda q, s, l: _genius_safe(q, "logic.classify_formula", q["formula"]),
    "genius_decide": lambda q, s, l: _genius_safe(
        q, "decision.compare", q["matrix"], q["labels"], q["criteria"],
        q.get("weights"), q.get("benefits"), method=str(q.get("method", "wsm"))),
    "genius_palette": lambda q, s, l: _genius_safe(
        q, "creative.palette", q["hex"], harmony=q.get("harmony", "analogous"),
        n=int(q.get("n", 5))),
    "genius_plan": lambda q, s, l: _genius_safe(q, "tasks.decompose", q["goal"]),
    "genius_sentiment": lambda q, s, l: _genius_safe(q, "language.sentiment", q["text"]),
    "genius_summarize": lambda q, s, l: _genius_safe(
        q, "language.summarize_focused", q["text"],
        q.get("query", ""), n_sentences=int(q.get("sentences", 3))),
    # ---- round-three ops (agent / scan / optimize / prefs / conformal) ----
    "agent_plan": lambda q, s, l: _agent_plan(q),
    "agent_simulate": lambda q, s, l: _agent_simulate(q),
    "scan_text": lambda q, s, l: _scan_text(q),
    "brief": lambda q, s, l: _brief(l),
    "tidy_survey": lambda q, s, l: _tidy_survey(q),
    "optimize_recommend": lambda q, s, l: _optimize_recommend(q),
    "optimize_score": lambda q, s, l: _optimize_score(q),
    "prefs_report": lambda q, s, l: _prefs_report(l),
    "conformal_verdict": lambda q, s, l: _conformal_verdict(q, s),
}


def _telemetry_snapshot(q):
    """One on-demand /proc + /sys read (issue #120 Phase 3.1). Not a
    daemon: every call is exactly one snapshot the caller asked for."""
    from ..diagnostics import telemetry
    return telemetry.snapshot(proc_dir=str(q.get("proc_dir", "/proc")),
                              sys_dir=str(q.get("sys_dir", "/sys")))


def _cortex_state(state_path):
    return st.load(state_path) if state_path else {}


def _agent_plan(q):
    from ..agent import goals
    return goals.decompose(str(q.get("text", "")))


def _agent_simulate(q):
    from ..agent.engine import Agent
    return Agent().simulate(str(q.get("text", "")))


def _scan_text(q):
    from ..scan import Automaton, scan_text
    patterns = [str(p) for p in q.get("patterns", [
        "quickshell", "kwin", "dbus", "error", "critical", "segfault",
        "failed to", "timeout"])]
    return scan_text(str(q.get("text", "")), Automaton(patterns),
                     chunk_size=int(q.get("chunk", 500)))


def _brief(ledger_path):
    from . import brief as brief_mod
    from .ledger import Ledger
    b = brief_mod.compose(pending=Ledger(ledger_path).pending())
    return {"brief": b, "rendered": brief_mod.render(b)}


def _tidy_survey(q):
    from . import tidy as tidy_mod
    plan = tidy_mod.survey(str(q.get("root", "~/Downloads")))
    return {"rendered": tidy_mod.render_plan(plan), **{
        k: plan[k] for k in ("root", "scanned", "type_moves", "duplicates",
                             "stale", "big_files", "empty_dirs",
                             "space_recoverable", "inert_suggestions")}}


def _optimize_recommend(q):
    from ..settings import optimize as opt
    return opt.recommend(str(q.get("profile", "gaming")),
                         k=int(q.get("k", 6)))


def _optimize_score(q):
    from ..settings import optimize as opt
    return opt.score_plan(str(q.get("profile", "gaming")),
                          list(q.get("ops", [])))


def _prefs_report(ledger_path):
    from . import prefs as prefs_mod
    from .ledger import Ledger
    model = prefs_mod.PreferenceModel()
    n = model.from_ledger(Ledger(ledger_path).items)
    biases = [model.bias(*key.split("|")[:2], int(key.split("|")[2]))
              for key in sorted(model.table.keys())[:12]]
    return {"decisions_learned": n, "biases": biases}


def _conformal_verdict(q, state_path):
    from ..cortex.conformal import ConformalCalibrator
    state = _cortex_state(state_path)
    cal = ConformalCalibrator()
    data = state.get("conformal")
    if data:
        cal.from_dict(data)
    for obs in q.get("calibration", []):
        cal.observe(float(obs.get("score", 0.0)), str(obs.get("outcome", "rejected")))
    return cal.verdict(float(q.get("score", 0.0)),
                       alpha=float(q.get("alpha", 0.1))) if cal.scores else \
        {"covered": None, "reason": "no calibration data in state", "score": q.get("score")}


def _genius_safe(q, dotted, *args, **kwargs):
    """Call a genius capability by dotted path, catching its honest errors.

    Only known (module, function) pairs on an explicit allow-list can ever
    run — the bridge cannot be pointed at arbitrary code.
    """
    from ..genius import (creative, decision, language, logic, mathengine,  # noqa: F401
                          stats, tasks)
    allowed = {
        "mathengine.expression_info": mathengine.expression_info,
        "stats.describe": stats.describe,
        "logic.classify_formula": logic.classify_formula,
        "decision.compare": decision.compare,
        "creative.palette": creative.palette,
        "tasks.decompose": tasks.decompose,
        "language.sentiment": language.sentiment,
        "language.summarize_focused": language.summarize_focused,
    }
    fn = allowed.get(dotted)
    if fn is None:
        return {"error": f"unknown genius op {dotted!r}"}
    try:
        return fn(*args, **kwargs)
    except (ValueError, KeyError, TypeError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _genius_do(q, state_path):
    from ..genius import meta as genius_meta

    state = _cortex_state(state_path)
    return genius_meta.route_and_do(q["text"], state.get("genius_learn"))


def _genius_learn(q, state_path):
    from ..genius import meta as genius_meta

    state = _cortex_state(state_path)
    table = genius_meta.learn_feedback(q["text"], q["domain"],
                                        bool(q["accepted"]),
                                        state.get("genius_learn"))
    state["genius_learn"] = table
    st.save(state, state_path)
    return {"updated": True, "domains_trained": sorted(table)}


def _genius_report(state_path, ledger_path):
    import json as _json
    from pathlib import Path as _Path

    from ..genius import metacog

    state = _cortex_state(state_path)
    ledger_file = _Path(ledger_path)
    proposals = (_json.loads(ledger_file.read_text()).get("proposals", [])
                 if ledger_file.exists() else [])
    usage = [{"domain": p.get("kind", "unknown"),
              "accepted": p.get("status") == "approved", "day": 1}
             for p in proposals if p.get("status") in ("approved", "rejected")]
    history = [{"features": {"kind": p.get("kind", "?"),
                             "confidence": "high" if p.get("confidence", 0) >= 0.7 else "low"},
                "outcome": "approve" if p.get("status") == "approved" else "reject"}
               for p in proposals if p.get("status") in ("approved", "rejected")]
    return {"coverage": metacog.coverage_map(usage),
            "learned_rules": metacog.induce_rules(history),
            "learned_routing": state.get("genius_learn")}


def _cortex_route(q, state_path):
    from ..cortex.learn import CortexLearner
    from ..cortex.pipeline import process as cortex_process

    learner = CortexLearner(_cortex_state(state_path).get("cortex_learn"))
    result = cortex_process(q["text"], learner=learner,
                            file_path=q.get("file"),
                            router_state=None)
    return result.to_dict()


def _cortex_chat_turn(q, state_path):
    """One conversational turn over the JSON bridge: pass the session
    dict from the previous response back in (``session`` key), get the
    updated session plus this turn's result. Read-only."""
    from ..cortex.learn import CortexLearner
    from ..cortex.pipeline import process as cortex_process
    from ..cortex.session import SessionState

    session = SessionState.from_dict(q.get("session"))
    learner = CortexLearner(_cortex_state(state_path).get("cortex_learn"))
    result = cortex_process(q["text"], session=session, learner=learner,
                            file_path=q.get("file"))
    return {"result": result.to_dict(), "session": session.to_dict()}


def _cortex_dispatch(q, state_path):
    """The unified local-vs-cloud decision point (the sidebar's ONLY
    routing authority): run the local cortex pipeline, and either answer
    locally or hand off to the cloud tier with a reason. A hand-off is
    logged into the bounded ``cortex_gaps`` state bucket (query shape +
    intent category, never raw text) before the state is saved — the
    single write this op performs, alongside the review bucket it shares
    with the CLI chat loop."""
    from ..cortex.dispatch import dispatch
    from ..cortex.session import SessionState

    state = _cortex_state(state_path)
    outcome = dispatch(q["text"], state=state,
                       session=SessionState.from_dict(q.get("session")),
                       file_path=q.get("file"))
    st.save(state, state_path)
    return outcome


def _cortex_gap_report(state_path):
    """Read-only clustering summary of the logged local-ontology gaps
    (minimum-support + purity floor applied — see cortex.dispatch)."""
    from ..cortex.dispatch import cluster_gaps

    return cluster_gaps(_cortex_state(state_path))


def _cortex_gap_propose(state_path, ledger_path):
    """Turn qualifying gap clusters into pending LEDGER PROPOSALS (kind
    ``ontology_gap"). Proposes, never applies — the ledger flow decides."""
    from ..cortex.dispatch import propose_gap_clusters
    from .ledger import Ledger

    state = _cortex_state(state_path)
    return propose_gap_clusters(state, Ledger(ledger_path))


def _cortex_report(state_path):
    from ..cortex.learn import CortexLearner
    from ..cortex.memory import summarize

    state = _cortex_state(state_path)
    learner = CortexLearner(state.get("cortex_learn"))
    episodes = list(state.get("cortex_memory") or [])
    return {"learning": learner.report(), "memory": summarize(episodes)}


def _cortex_memory_recall(q, state_path):
    from ..cortex.memory import recall

    episodes = list(_cortex_state(state_path).get("cortex_memory") or [])
    return recall(episodes, q.get("query", ""), k=int(q.get("k", 10)))


def _cortex_learn_feedback(q, state_path):
    """Report an outcome for a learn_hook the caller received: the
    learning loop's only entry point from the shell side. The same (p,
    outcome) pair also feeds the conformal calibrator's history (state key
    ``conformal``), so its distribution-free verdicts accumulate real
    data instead of living only inside one bridge call."""
    from ..cortex.conformal import ConformalCalibrator
    from ..cortex.learn import CortexLearner

    state = _cortex_state(state_path)
    learner = CortexLearner(state.get("cortex_learn"))
    learner.observe(q["text"], q.get("surface", ""), q.get("features", {}),
                    float(q.get("p", 0.0)), q["outcome"])
    if q.get("strategy"):
        learner.reward_strategy(str(q["strategy"]), q["outcome"] in ("applied", "approved"))
    state["cortex_learn"] = learner.to_dict()
    cal = ConformalCalibrator()
    data = state.get("conformal")
    if isinstance(data, dict):
        cal.from_dict(data)
    cal.observe(float(q.get("p", 0.0)), str(q["outcome"]))
    state["conformal"] = cal.to_dict()
    st.save(state, state_path)
    return {"examples": learner.model.examples,
            "acceptance_rate": round(learner.accepts / max(1, learner.accepts + learner.rejects), 3)}


def handle(request, state_path=str(st.DEFAULT_STATE), ledger_path=str(DEFAULT_LEDGER)):
    if not isinstance(request, dict):
        return {"ok": False, "op": None, "error": "request must be a JSON object"}
    op = request.get("op")
    if op not in OPS:
        return {"ok": False, "op": op,
                "error": f"unknown op; expected one of: {', '.join(sorted(OPS))}"}
    try:
        result = OPS[op](request, state_path, ledger_path)
    except (KeyError, TypeError, ValueError) as e:
        return {"ok": False, "op": op, "error": f"{type(e).__name__}: {e}"}
    except OSError as e:
        return {"ok": False, "op": op, "error": f"io error: {e}"}
    return {"ok": True, "op": op, "result": result}


def main(argv=None, stdin_text=None, out=None):
    p = argparse.ArgumentParser(prog="caelestia-assist api", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", default=str(st.DEFAULT_STATE))
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    args = p.parse_args(argv)
    text = sys.stdin.read() if stdin_text is None else stdin_text
    try:
        request = json.loads(text)
    except json.JSONDecodeError as e:
        response = {"ok": False, "op": None, "error": f"invalid JSON: {e}"}
    else:
        response = handle(request, args.state, args.ledger)
    (out or sys.stdout).write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
    return 0 if response["ok"] else 1
