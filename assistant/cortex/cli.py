"""CLI surface for the cortex layer: ``chat``, ``route``, ``cortex``.

Commands (routed by hub.py):

  caelestia-assist chat [--json] [--file PATH] [--apply-confirmed]
      Interactive conversational REPL. Every routed plan is shown with
      evidence and a calibrated confidence; NOTHING writes until the
      y/N prompt answers y (the multi-change confirmation gate issue
      #120 asks for, in conversational form). ``--json`` switches to a
      line-delimited JSON protocol for the QML bridge / scripts — pure
      information unless ``--apply-confirmed`` ALSO asserts the
      caller's own confirmation UI was used.

  caelestia-assist route "text" [--file PATH] [--json] [-k N]
      One-shot: route + plan + evidence, no interaction, never writes.

  caelestia-assist cortex report|recall|reset-learning|suggest
      The self-learning and memory dashboard: calibration, strategy
      bandit, drift, episodic recall, and the proactive co-change
      suggestion (as a ledger proposal — ``suggest`` never applies).

State lives in the brain's state.json (keys ``cortex_learn`` and
``cortex_memory``), written through the same atomic-save path as every
other learned model. The chat/session state itself is per-process.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..brain import state as brain_state
from ..settings import applier as settings_applier
from ..settings import consequences
from ..settings import history as settings_history
from ..settings import planner as settings_planner
from ..settings.cli import default_target, render_plan
from . import learn as cortex_learn
from .delegate import run_delegate, runner_names
from .learn import CortexLearner
from .memory import (
    followup_suggestion,
    record as memory_record,
    recall as memory_recall,
    resolve_halflife,
    summarize as memory_summarize,
)
from .pipeline import episode_for, process as cortex_process
from .plans import DISCARD_RE, PlanCache
from .session import SessionState

LEARN_KEY = "cortex_learn"
MEMORY_KEY = "cortex_memory"


# ---------------------------------------------------------------------------
# Shared state helpers.
# ---------------------------------------------------------------------------


def _load_learner(state: Optional[Dict[str, Any]] = None) -> CortexLearner:
    data = state if state is not None else brain_state.load()
    return CortexLearner(data.get(LEARN_KEY))  # type: ignore[arg-type]


def _load_memory(state: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    data = state if state is not None else brain_state.load()
    raw = data.get(MEMORY_KEY) or []
    return [dict(row) for row in raw]  # type: ignore[union-attr]


def _now() -> datetime:
    return datetime.now()


# ---------------------------------------------------------------------------
# Rendering.
# ---------------------------------------------------------------------------


def _fmt_candidates(result) -> List[str]:
    lines = []
    for cand in result.candidates[:5]:
        marker = "->" if cand is result.candidates[0] else "  "
        lines.append(f"{marker} {cand['surface']}  (score {cand['score']:.3f}, "
                     f"kind {cand['kind']})")
    return lines


def _render_genius(genius_result: Dict[str, object]) -> None:
    """Compact renderer for an inline genius answer inside cortex turns."""
    from .delegate import _format_genius

    for line in _format_genius(dict(genius_result)):
        print(line)


def _render_turn(result, *, applied: bool = False,
                 inline_delegate: bool = False) -> List[str]:
    """Human rendering of one cortex result (the chat card).

    ``inline_delegate``: the DELEGATE target already ran inline this turn
    (its answer follows this card), so the "try:" hint is suppressed —
    it stays the fallback for the rare case the inline run itself fails.
    """
    lines: List[str] = []
    verdict_label = {
        "PLAN": "FOUND A CHANGE" if applied else "PROPOSED CHANGE",
        "QUESTION": "NEED A DETAIL",
        "ABSTAIN": "NO MATCH",
        "DELEGATE": "OTHER LAYER",
        "EXPLAIN": "EXPLANATION",
        "UNDO": "UNDO",
        "LIST": "HISTORY",
        "INERT": "OUTSIDE SHELL.JSON",
    }.get(result.verdict, result.verdict)
    lines.append(f"[cortex] {verdict_label}  (confidence {result.confidence:.2f}"
                 + (f", strategy {result.strategy}" if result.strategy else "") + ")")
    if result.session_note:
        lines.append(f"  {result.session_note}")
    lines.extend(f"  {line}" for line in _fmt_candidates(result))
    if result.evidence:
        shown = "; ".join(dict.fromkeys(result.evidence))[:220]
        lines.append(f"  evidence: {shown}")
    if result.verdict == "PLAN" and result.plan is not None:
        lines.append("")
        lines.extend("  " + line for line in render_plan(
            result.plan, [], "cortex chat", None, applied, None, None))
    if result.verdict == "QUESTION":
        lines.extend(f"  ? {q}" for q in result.questions)
    if result.verdict == "EXPLAIN" and result.explain_answer:
        lines.append(f"  {result.explain_answer.get('answer', '')}")
        cites = result.explain_answer.get("cites") or []
        if cites:
            lines.append(f"  grounded in: {'; '.join(str(c) for c in cites)}")
    if result.history_plan:
        hp = result.history_plan
        lines.append(f"  {hp.get('reason', '')}")
        for entry in hp.get("entries", [])[:5]:
            label = entry.get("label") or f"#{entry.get('id')}"
            lines.append(f"    - [{entry.get('id')}] {label} at {entry.get('at')}")
    if result.delegate and not inline_delegate:
        hint = {
            "diagnose": "caelestia-assist diagnose <file>",
            "search": "caelestia-assist search \"...\"",
            "brain": "caelestia-assist brain --help",
            "issue": "caelestia-assist issue draft --title ...",
            "agent": "caelestia-assist agent \"...\" --simulate",
        }.get(result.delegate, result.delegate)
        lines.append(f"  try: {hint}")
    if result.suggestions:
        lines.extend(f"  {s}" for s in result.suggestions)
    for note in result.notes[:6]:
        if note:
            lines.append(f"  note: {note}")
    return lines


def _render_report(learner: CortexLearner, episodes: List[Dict[str, object]]) -> List[str]:
    report = learner.report()
    memory = memory_summarize(episodes)
    lines = [
        "cortex — learned intelligence report",
        f"  routing examples observed : {report['examples']} "
        f"({report['accepts']} accepted / {report['rejects']} rejected)",
        f"  acceptance rate           : {report['acceptance_rate']}",
        f"  calibration (overall)     : {report['calibration']['overall']}",
    ]
    for bucket, mean in report["calibration"]["buckets"].items():
        lines.append(f"    {bucket:8s}: {mean}")
    lines.append("  strategy arms (Thompson):")
    for name, row in report["strategy_arms"].items():
        lines.append(f"    {name:10s}: mean {row['mean']} over {row['draws']} draws")
    lines.append(f"  fitted signal weights     : {report['fitted_weights']}")
    lines.append(f"  drift                     : {report['drift']}")
    lines.append(f"  memory episodes           : {memory['episodes']} "
                 f"({memory['applied_episodes']} applied)")
    if memory["top_surfaces"]:
        tops = ", ".join(f"{row['surface']}({row['count']})" for row in memory["top_surfaces"][:5])
        lines.append(f"  most-changed settings     : {tops}")
    if memory["top_cochanges"]:
        pairs = ", ".join(f"{row['a']}+{row['b']} (lift {row['lift']})" for row in memory["top_cochanges"][:3])
        lines.append(f"  strongest co-changes      : {pairs}")
    if memory["peak_hour"] is not None:
        lines.append(f"  customization peak hour   : {memory['peak_hour']}:00")
    return lines


# ---------------------------------------------------------------------------
# The chat REPL.
# ---------------------------------------------------------------------------


def _confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def _apply_plan(result, target: Path, text: str) -> bool:
    """The one write path of the chat — the existing applier, gated by
    the interactive confirmation (issue #120's multi-change gate)."""
    if result.plan is None:
        return False
    if not _confirm("apply these changes?"):
        return False
    try:
        settings_applier.apply(result.plan, target, write=True, label=f"chat: {text}")
    except settings_applier.ApplierError as exc:
        print(f"  error: {exc}", file=sys.stderr)
        return False
    return True


def _run_undo(result, target: Path) -> bool:
    if not result.history_plan:
        return False
    action = result.history_plan.get("action")
    try:
        if action == "undo":
            steps = int(result.history_plan.get("steps") or 1)
            if not _confirm(f"undo the last {steps} change(s)?"):
                return False
            outcome = settings_history.undo(target, steps=steps)
        elif action == "undo_by_id":
            entry_id = int(result.history_plan.get("entry_id") or 0)
            if not _confirm(f"revert history entry #{entry_id}?"):
                return False
            outcome = settings_history.undo_by_id(target, entry_id=entry_id)
        else:
            return False
    except settings_history.HistoryError as exc:
        print(f"  error: {exc}", file=sys.stderr)
        return False
    print(f"  restored: {bool(outcome.get('restored') or outcome.get('written'))}"
          + (f" — {outcome.get('message', '')}" if outcome.get("message") else ""))
    return bool(outcome.get("restored") or outcome.get("written"))


def cmd_chat(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="caelestia-assist chat",
        description="conversational settings assistant (learned routing, "
                    "confirmation-gated applies, never writes without y)",
    )
    parser.add_argument("--file", default=None, help="target shell.json override")
    parser.add_argument("--json", action="store_true",
                        help="line-delimited JSON protocol per turn (machine mode)")
    parser.add_argument("--apply-confirmed", action="store_true",
                        help="JSON mode only: the caller asserts its own confirmation "
                             "UI was used; single-op plans apply without the y/N prompt")
    parser.add_argument("--no-learn", action="store_true",
                        help="do not read or update learned state this session")
    args = parser.parse_args(argv)

    target = Path(args.file) if args.file else default_target()
    state = brain_state.load()
    learner = None if args.no_learn else _load_learner(state)
    episodes = _load_memory(state)
    review_bucket = list(state.get("cortex_review", []))
    session = SessionState()
    plan_cache = PlanCache.from_dict(session.pending_plan)

    print(f"cortex chat — natural-language shell.json assistant")
    print(f"target: {target}")
    print("commands: /exit /history /undo N | everything else is a request")
    if args.json:
        print(json.dumps({"type": "session", "target": str(target), "apply_allowed": bool(args.apply_confirmed)}))

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        if text in ("/exit", "/quit", "/q"):
            break
        if text == "/history":
            for turn in session.to_dict()["turns"]:
                print(f"  you: {turn['text']}  ->  {', '.join(turn['surfaces']) or turn['verdict']}")
            continue
        if text.startswith("/undo"):
            parts = text.split()
            steps = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            try:
                outcome = settings_history.undo(target, steps=steps)
            except settings_history.HistoryError as exc:
                print(f"  error: {exc}", file=sys.stderr)
                continue
            print(f"  restored: {bool(outcome.get('restored'))}")
            continue

        # Phase 2.5: explicit discard drops the pending plan (the honest
        # way out of an iteration, instead of refusing it forever).
        if DISCARD_RE.match(text):
            dropped = plan_cache.pending_count()
            plan_cache.discard()
            session.pending_plan = None
            print(f"  discarded {dropped} pending change(s)")
            continue

        # Phase 2.5: an explicit APPLY of the accumulated pending plan —
        # recognized BEFORE the session's yes-answer machinery can eat it
        # ("apply" is also a yes-word there; here it is an instruction).
        if (re.match(r"^\s*(?:apply|apply these|apply these changes|"
                     r"apply them|apply it|go ahead|commit)\s*[.!]?\s*$",
                     text, re.IGNORECASE)
                and plan_cache.pending_count() > 0):
            pending_ops = plan_cache.pending()
            class _ApplyResult:  # minimal shape _apply_plan needs
                plan = None
            try:
                apply_result = _ApplyResult()
                apply_result.plan = settings_planner.plan(pending_ops,
                                                          target)
            except settings_planner.PlannerError as exc:
                print(f"  error: composed plan refused: {exc}",
                      file=sys.stderr)
                continue
            if _apply_plan(apply_result, target, "pending plan"):
                plan_cache.commit()
                session.pending_plan = None
                print(f"  applied {len(pending_ops)} composed change(s) "
                      "(backup written; 'undo the last change' reverts it)")
            else:
                session.pending_plan = plan_cache.to_dict()
                pending_line = plan_cache.summary()
                print(f"  {pending_line} — still pending (refused)")
            continue

        # Phase 2.7: what-if turns render the CONSEQUENCE view for the
        # composed plan (pending + this request) and never gate an apply —
        # iterate first, commit later.
        if re.match(r"^\s*what\s+if\b", text, re.IGNORECASE):
            whatif_text = re.sub(r"^\s*what\s+if\b", "", text,
                                 flags=re.IGNORECASE).strip()
            if whatif_text:
                # "what if X" — plan X (read-only), compose it with the
                # pending plan, and project the CONSEQUENCES.
                whatif_result = cortex_process(
                    whatif_text, session=session, learner=learner,
                    file_path=target, now=_now())
                new_ops = whatif_result.ops or []
            else:
                # A BARE "what if" projects the pending plan itself — it
                # must NOT route a placeholder request (the router's
                # fuzzy match on "show my pending changes" once resolved
                # to a toast toggle and polluted the pending plan).
                new_ops = []
            ops = new_ops or plan_cache.pending()
            if ops:
                if new_ops:
                    ops = plan_cache.compose(new_ops, whatif_text)
                current: Dict[str, Any] = {}
                if target.exists():
                    try:
                        current, _notes = settings_planner._read_current(
                            target)
                    except Exception:
                        current = {}
                # The composed RAW ops (later-wins per tool, mirroring
                # the compound layer) re-validate through the standard
                # planner; the PROJECTION then runs over the planner's
                # RESOLVED entries — step/multiply ops become absolute
                # values, never raw deltas (projecting a step delta of
                # -1 as an absolute scale was a real bug this pins).
                resolved_ops: List[Dict[str, Any]] = []
                try:
                    composed_plan = settings_planner.plan(ops, target)
                    resolved_ops = [
                        {"tool": e.get("tool"), "value": e.get("new")}
                        for e in composed_plan.get("entries", [])
                        if not e.get("error")]
                except settings_planner.PlannerError:
                    pass  # the consequence view renders regardless
                projection = consequences.project(
                    resolved_ops or ops, current=current)
                if args.json:
                    print(json.dumps({"type": "whatif", "projection":
                                      projection}, default=str))
                else:
                    print("\n".join(consequences.render(
                        projection, title="what-if")))
                    pending_line = plan_cache.summary()
                    if pending_line:
                        print(f"  {pending_line}")
                        print("  say the next change, or 'apply these "
                              "changes' when ready")
                session.pending_plan = plan_cache.to_dict()
            else:
                print("  nothing to project: no ops in this request and "
                      "no pending plan")
            continue

        result = cortex_process(text, session=session, learner=learner, file_path=target, now=_now())

        # Phase 2.5: compose this turn's ops with the PENDING plan (later
        # wins per tool — the compound layer's own rule) and re-validate
        # through the standard planner before proposing anything.
        if result.verdict == "PLAN" and result.ops:
            if plan_cache.pending_count() > 0:
                composed_ops = plan_cache.compose(result.ops, text)
                try:
                    composed_plan = settings_planner.plan(composed_ops,
                                                          target)
                    result.plan = composed_plan
                    result.ops = composed_ops
                    result.session_note = (
                        (result.session_note + " " if result.session_note
                         else "") + f"composed with your pending plan "
                        f"({plan_cache.pending_count()} ops total)")
                except settings_planner.PlannerError as exc:
                    result.notes.append(f"composed plan refused: {exc}")
            else:
                plan_cache.compose(result.ops, text)

        # Issue #120 phase 4.3: near-threshold phrases are parked for batch
        # review instead of being silently absorbed by the online learner.
        if cortex_learn.is_near_threshold(result.verdict):
            review_bucket = cortex_learn.log_review_candidate(
                review_bucket, text, result.verdict,
                result.candidates or [], at=_now())

        # Inline delegation (routing fix, phase 1.2/1.3): the DELEGATE
        # target runs in this turn — genius (as before, now generalized),
        # diagnose, search, brain, issue, and the agent's simulated task
        # graph. A failed inline run degrades to the hint card below.
        if result.verdict == "DELEGATE" and result.delegate in runner_names():
            inline = run_delegate(result.delegate, text, state)
            if inline is not None:
                payload, inline_lines = inline
                if args.json:
                    print(json.dumps(
                        {"type": "turn", "verdict": "DELEGATE",
                         "delegate": result.delegate,
                         result.delegate: payload}, default=str))
                else:
                    print("\n".join(_render_turn(result, inline_delegate=True)))
                    print("\n".join(inline_lines))
                if learner is not None:
                    episodes = memory_record(episodes,
                                             episode_for(result, text, "routed", now=_now()))
                continue
            result.notes.append(
                f"inline {result.delegate} run failed — the fallback hint stands")

        # Calibration surfacing (phase 2.4): the honest line users can
        # hold the assistant to — observed accuracy for THIS confidence
        # bucket, only when the sample can support a claim. The bucket
        # key is the RAW route probability (learn_hook carries it); the
        # calibrated confidence is a different quantity.
        raw_p = ((result.learn_hook or {}).get("p", result.confidence)
                 if result.learn_hook is not None else result.confidence)
        calibration_note = (learner.calibration_note(raw_p)
                            if learner is not None else None)

        applied = False
        undone = False
        if result.verdict == "PLAN":
            if args.json:
                if args.apply_confirmed and result.plan and len(result.plan.get("entries", [])) == 1:
                    try:
                        settings_applier.apply(result.plan, target, write=True, label=f"chat: {text}")
                        applied = True
                    except settings_applier.ApplierError as exc:
                        result.notes.append(f"apply failed: {exc}")
            else:
                applied = _apply_plan(result, target, text)
        elif result.verdict == "UNDO":
            if not args.json:
                undone = _run_undo(result, target)

        if args.json:
            payload = result.to_dict()
            payload["type"] = "turn"
            payload["applied"] = applied
            payload["undone"] = undone
            print(json.dumps(payload))
        else:
            card = _render_turn(result, applied=applied)
            if calibration_note:
                card.append(f"  {calibration_note}")
            print("\n".join(card))
            if applied:
                plan_cache.commit()
                session.pending_plan = None
                print("  applied (backup written; 'undo the last change' "
                      "reverts it)")
            elif result.verdict == "PLAN" and plan_cache.pending_count():
                session.pending_plan = plan_cache.to_dict()
                pending_line = plan_cache.summary()
                if pending_line:
                    print(f"  {pending_line} — compose the next change or "
                          "say 'apply these changes'")

        # Learning + memory (persisted through the brain state).
        if learner is not None:
            outcome = ("applied" if applied else
                       "undone" if undone else
                       "rejected" if result.verdict == "PLAN" else
                       "clarified" if result.verdict == "QUESTION" else
                       "routed" if result.verdict == "PLAN" else result.verdict.lower())
            if result.learn_hook is not None:
                hook = result.learn_hook
                learner.observe(hook["text"], hook["surface"], hook["features"],
                                hook["p"], outcome)
            if applied and result.learn_hook is not None:
                learner.reward_strategy(result.strategy or "balanced", True)
            elif result.verdict == "PLAN" and not applied:
                learner.reward_strategy(result.strategy or "balanced", False)
            episodes = memory_record(episodes, episode_for(result, text, outcome, now=_now()))
            # Proactive follow-up (second-brain suggestion, proposal only).
            if applied and result.candidates:
                suggestions = followup_suggestion(
                    episodes, result.candidates[0]["surface"], now=_now(),
                    halflife_days=resolve_halflife(state))
                for suggestion in suggestions[:1]:
                    print(f"  suggestion: you often also change {suggestion['surface']} "
                          f"({suggestion['count']}x together) — say '{suggestion['surface'].replace('set', 'change ').strip()}' "
                          f"if you want it proposed")

    if learner is not None or episodes or review_bucket:
        state = brain_state.load()
        state[LEARN_KEY] = learner.to_dict() if learner is not None else state.get(LEARN_KEY)
        state[MEMORY_KEY] = episodes
        state["cortex_review"] = review_bucket
        brain_state.save(state)
    if not args.json:
        print("session ended; learned routing and memory updated")
    return 0


# ---------------------------------------------------------------------------
# One-shot route.
# ---------------------------------------------------------------------------


def cmd_route(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="caelestia-assist route",
        description="one-shot universal routing: any phrase -> ranked surfaces + "
                    "validated plan (read-only, never writes)",
    )
    parser.add_argument("text", help="the request phrase")
    parser.add_argument("--file", default=None, help="target shell.json override")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("-k", type=int, default=5, help="top-k candidates")
    args = parser.parse_args(argv)

    target = Path(args.file) if args.file else default_target()
    state = brain_state.load()
    learner = _load_learner(state)
    result = cortex_process(args.text, learner=learner, file_path=target, now=_now())
    # Inline delegation (routing fix, phase 1.2/1.3): one-shot answers the
    # same way the chat REPL does — run the target layer inline, render in
    # the same turn; a failed run falls through to the hint card.
    if result.verdict == "DELEGATE" and result.delegate in runner_names():
        inline = run_delegate(result.delegate, args.text, state)
        if inline is not None:
            payload, inline_lines = inline
            if args.json:
                print(json.dumps({"verdict": "DELEGATE", "delegate": result.delegate,
                                  result.delegate: payload}, default=str))
            else:
                print("\n".join(_render_turn(result, inline_delegate=True)))
                print("\n".join(inline_lines))
            return 0
        result.notes.append(
            f"inline {result.delegate} run failed — the fallback hint stands")
    if args.json:
        print(json.dumps(result.to_dict()))
    else:
        print("\n".join(_render_turn(result)))
    return 0


# ---------------------------------------------------------------------------
# Cortex management (report / recall / reset-learning / suggest).
# ---------------------------------------------------------------------------


def cmd_cortex(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="caelestia-assist cortex",
        description="the learned-intelligence dashboard: calibration, strategies, "
                    "drift, episodic memory, co-change suggestions",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report", help="learning + memory report")
    recall_p = sub.add_parser("recall", help="recall past interactions")
    recall_p.add_argument("query", nargs="?", default="", help="surface or text filter")
    recall_p.add_argument("-k", type=int, default=10)
    sub.add_parser("reset-learning", help="wipe learned routing weights (memory kept)")
    suggest_p = sub.add_parser("suggest", help="co-change follow-up suggestions")
    suggest_p.add_argument("surface", help="tool name just applied (e.g. setBarScale)")
    suggest_p.add_argument("--apply", action="store_true",
                           help="record the suggestion as a pending LEDGER proposal "
                                "(still needs ledger approve to write)")
    review_p = sub.add_parser("review", help="batch-review near-threshold phrases "
                                              "(logged, never silently "
                                              "learned)")
    review_p.add_argument("action", nargs="?", default="list",
                          choices=["list", "label", "dismiss"])
    review_p.add_argument("arg1", nargs="?", default="",
                          help="label/dismiss: the candidate index (see list)")
    review_p.add_argument("arg2", nargs="?", default="",
                          help="label: the correct surface (e.g. setBarScale)")
    hl = sub.add_parser("halflife", help="read or set the memory decay "
                                         "half-life in days (user-editable; "
                                         "default 14, bounds 0.5-365)")
    hl.add_argument("days", nargs="?", type=float, default=None,
                    help="new half-life in days (omit to read)")
    gaps_p = sub.add_parser("gaps", help="cluster the logged local-ontology gaps "
                                         "(cloud hand-offs) and surface candidates")
    gaps_p.add_argument("--propose", action="store_true",
                        help="record qualifying clusters as pending LEDGER "
                             "proposals (kind ontology_gap; approve/reject "
                             "decides — never auto-applied)")
    gaps_p.add_argument("--min-support", type=int, default=3,
                        help="minimum requests per cluster (default 3, the "
                             "workspace.py floor)")
    gaps_p.add_argument("--purity", type=float, default=0.6,
                        help="minimum modal-shape coverage (default 0.6, the "
                             "workspace.py floor)")
    lex_p = sub.add_parser("lexicon", help="federated, opt-in, signed "
                                            "lexicon-diff sharing "
                                            "(export/import/forget; no network, "
                                            "no auto-merge — verify signatures "
                                            "with YOUR external tool)")
    lex_p.add_argument("action", choices=["export", "import", "forget",
                                           "list", "trust"],
                       help="export: print the reviewable diff; import: apply a "
                            "diff from stdin as supervised pairs; forget: drop "
                            "one imported set by id; list: imported sets; "
                            "trust: the ADVISORY signer trust view (never "
                            "auto-decides anything)")
    lex_p.add_argument("diff_id", nargs="?", default="",
                       help="forget: the diff id to drop (see list)")
    lex_p.add_argument("--signer", default=None,
                       help="import: the identity YOU verified with your own "
                            "tool (minisign/sq/gpg) — recorded for the "
                            "advisory trust history only", )
    args = parser.parse_args(argv)

    state = brain_state.load()
    learner = _load_learner(state)
    episodes = _load_memory(state)

    if args.cmd == "halflife":
        from .memory import (HALFLIFE_BOUNDS, HALFLIFE_DAYS, MEMORY_HALFLIFE_KEY,
                             resolve_halflife)
        if args.days is None:
            print(f"memory decay half-life: {resolve_halflife(state)} days "
                  f"(default {HALFLIFE_DAYS}; bounds "
                  f"{HALFLIFE_BOUNDS[0]}-{HALFLIFE_BOUNDS[1]})")
            return 0
        lo, hi = HALFLIFE_BOUNDS
        if not (lo <= args.days <= hi):
            print(f"error: half-life must be within {lo}-{hi} days",
                  file=sys.stderr)
            return 1
        state[MEMORY_HALFLIFE_KEY] = args.days
        brain_state.save(state)
        print(f"memory decay half-life set to {args.days} days "
              "(affects recall weighting from now on; history untouched)")
        return 0

    if args.cmd == "lexicon":
        from .. import capabilities
        if not capabilities.enabled("lexicon_sharing"):
            print("error: lexicon_sharing is disabled in the capability "
                  "manifest (edit capabilities.json to enable; it cannot "
                  "be enabled by a request)", file=sys.stderr)
            return 1
        from . import lexicon_diff
        if args.action == "export":
            rows = lexicon_diff.export_rows(state)
            if not rows:
                print("nothing learned to share yet (the learner's example "
                      "log is empty)")
                return 0
            sys.stdout.write(lexicon_diff.render(
                rows, date=datetime.now().strftime("%Y-%m-%d")))
            print("# export is read-only: sign it with YOUR external tool "
                  "(minisign/sq/gpg) before sharing", file=sys.stderr)
            return 0
        if args.action == "import":
            text = sys.stdin.read()
            report = lexicon_diff.import_diff(state, text, signer=args.signer)
            if "error" in report:
                print(f"error: {report['error']}", file=sys.stderr)
                for warn in report.get("warnings", []):
                    print(f"  warning: {warn}", file=sys.stderr)
                return 1
            brain_state.save(state)
            print(f"imported diff {report['diff_id']}: "
                  f"{report['imported']} pair(s)")
            print("  tools this diff boosts (review them):")
            for tool in report["boosted_tools"]:
                print(f"    - {tool}")
            for warn in report.get("warnings", []):
                print(f"  warning: {warn}")
            print(f"  {report['note']}")
            if report.get("signer_trust"):
                print(f"  {report['signer_trust']}")
            print(f"  {report['verify']}")
            print(f"  rollback: {report['rollback']}")
            return 0
        if args.action == "forget":
            report = lexicon_diff.forget(state, args.diff_id)
            if "error" in report:
                print(f"error: {report['error']}", file=sys.stderr)
                return 1
            brain_state.save(state)
            print(f"forgot {report['forgot']} "
                  f"({report['rows_dropped']} row(s)); {report['note']}")
            return 0
        if args.action == "trust":
            scores = lexicon_diff.signer_trust(state)
            if not scores:
                print("no signer history — imports without --signer "
                      "record nothing; trust starts at the flat prior")
                return 0
            print(lexicon_diff.render_advisory(scores))
            return 0
        # list
        ids = lexicon_diff.imported_ids(state)
        if not ids:
            print("no imported lexicon diffs")
            return 0
        imports = state.get(lexicon_diff.IMPORTS_KEY) or {}
        for did in ids:
            entry = imports.get(did) or {}
            print(f"  {did}  {entry.get('n', '?')} pair(s)")
        print("forget with: cortex lexicon forget <id>")
        return 0

    if args.cmd == "report":
        print("\n".join(_render_report(learner, episodes)))
        return 0

    if args.cmd == "recall":
        rows = memory_recall(episodes, args.query, now=_now(), k=args.k,
                             halflife_days=resolve_halflife(state))
        if not rows:
            print("no matching episodes in memory")
            return 0
        for row in rows:
            surfaces = ", ".join(str(s) for s in row.get("surfaces", []))
            print(f"  [{row.get('at')}] {row.get('outcome')}: {row.get('text')}"
                  + (f"  -> {surfaces}" if surfaces else ""))
        return 0

    if args.cmd == "reset-learning":
        state[LEARN_KEY] = CortexLearner().to_dict()
        brain_state.save(state)
        print("learned routing weights reset to priors (memory kept)")
        return 0

    if args.cmd == "review":
        from . import learn as cortex_learn
        bucket = list(state.get(cortex_learn.REVIEW_KEY, []))
        if args.action == "list":
            if not bucket:
                print("no near-threshold candidates logged yet (ambiguous or "
                      "abstained chat phrases land here)")
                return 0
            print(f"{len(bucket)} candidate(s), oldest last:")
            for i, c in enumerate(bucket):
                print(f"  [{i}] {c['verdict']:<8} p={c.get('p')} :: {c['text']}")
            print("label with: cortex review label INDEX SURFACE   "
                  "(teaches the router, nothing applies)")
            print("drop with:  cortex review dismiss INDEX")
            return 0
        if learner is None:
            print("learning is disabled (--no-learn or no state); cannot label",
                  file=sys.stderr)
            return 1
        try:
            if args.action == "label":
                if not args.arg1 or not args.arg2:
                    print("review label needs INDEX and SURFACE", file=sys.stderr)
                    return 2
                res = cortex_learn.label_candidate(state, int(args.arg1),
                                                   args.arg2, learner)
                state[LEARN_KEY] = learner.to_dict()
                brain_state.save(state)
                print(f"taught: {res['text']!r} -> {res['surface']} "
                      f"({res['remaining']} candidate(s) left)")
            else:
                res = cortex_learn.dismiss_candidate(state, int(args.arg1))
                brain_state.save(state)
                print(f"dismissed: {res['text']!r} ({res['remaining']} left)")
            return 0
        except (ValueError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if args.cmd == "gaps":
        from .dispatch import cluster_gaps, propose_gap_clusters
        from ..brain.cli import DEFAULT_LEDGER
        from ..brain.ledger import Ledger

        if args.propose:
            res = propose_gap_clusters(state, Ledger(DEFAULT_LEDGER),
                                      min_support=args.min_support,
                                      purity=args.purity)
            if res["proposals"]:
                print(f"{len(res['proposals'])} pending proposal(s) recorded "
                      f"(kind ontology_gap) — `caelestia-assist brain ledger` "
                      f"decides; nothing is applied automatically")
            else:
                print("no qualifying cluster reached the support/purity floor "
                      "— nothing proposed")
            summary = res["summary"]
        else:
            summary = cluster_gaps(state, min_support=args.min_support,
                                   purity=args.purity)
        print(f"local-ontology gaps: {summary['n_gaps']} logged shape(s); "
              f"k={summary['k']}, {summary['rejected_clusters']} cluster(s) "
              f"below the support/purity floor")
        if not summary["candidates"]:
            print("no candidate local tools — a handful of scattered gaps is "
                  "noise, not a need (by design)")
        for c in summary["candidates"]:
            print(f"  {c['support']}x  \"{c['label']}\"  "
                  f"(category {c['category']}, purity {c['purity']}, "
                  f"{c['shapes']} phrasing(s))")
        if summary["candidates"] and not args.propose:
            print("surface with: cortex gaps --propose  (ledger proposals, "
                  "never auto-applied)")
        return 0

    if args.cmd == "suggest":
        suggestions = followup_suggestion(episodes, args.surface, now=_now(),
                                           halflife_days=resolve_halflife(state))
        if not suggestions:
            print(f"no co-change pattern with {args.surface} yet "
                  f"(needs repeated applied history)")
            return 0
        for suggestion in suggestions:
            print(f"  {suggestion['surface']}: {suggestion['count']}x together, "
                  f"decay-weighted score {suggestion['weight']}")
        if args.apply:
            from ..brain import ledger as brain_ledger
            from ..brain import settings_bridge
            top = suggestions[0]["surface"]
            # brain/ledger.py exposes the Ledger class (no module-level
            # load/save helpers); use DEFAULT_LEDGER for continuity with the
            # brain CLI's proposal store.
            from ..brain.cli import DEFAULT_LEDGER
            ledger = brain_ledger.Ledger(DEFAULT_LEDGER)
            pid = settings_bridge.propose(
                ledger, str(default_target()), None, [], 
                reason=f"cortex co-change suggestion after {args.surface} "
                       f"({top} changed together {suggestions[0]['count']}x)",
                confidence=round(min(0.9, 0.4 + 0.1 * suggestions[0]["count"]), 2),
            )
            if pid is None:
                print("nothing to propose (the dry-run plan was blocked or a no-op)")
            else:
                print(f"ledger proposal {pid} created (approve with: "
                      f"caelestia-assist brain ledger approve {pid})")
        return 0

    return 2


# ---------------------------------------------------------------------------
# Entry points.
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else [])
    if not argv:
        argv = ["--help"]
    if argv[0] == "chat":
        return cmd_chat(argv[1:])
    if argv[0] == "route":
        return cmd_route(argv[1:])
    if argv[0] in ("report", "recall", "reset-learning", "suggest", "review"):
        return cmd_cortex(argv)
    return cmd_cortex(argv)


if __name__ == "__main__":
    raise SystemExit(main())
