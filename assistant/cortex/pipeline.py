"""The cortex pipeline: natural language in, validated plan out.

This is the integration seam between the learned intelligence layer and
the existing deterministic settings spine (issue #120's architecture,
unchanged beneath):

    text ─► session resolution ─► compound split ─► per-clause routing
         ─► cue→op value resolution ─► settings.planner.plan (VALIDATION)
         ─► {ops, plan, confidence, evidence, questions}

Safety spine (inherited, not reinvented):

- VALUE RESOLUTION IS HINTS-ONLY: the router's cues become relative ops
  (step ±1/±2, multiply) or absolute SETs; the planner resolves them
  against the live file, rejects out-of-range values (never clamps
  absolutes), and blocks the whole plan on any error. The pipeline adds
  zero write paths — ``settings.applier.apply`` remains the only writer.
- PRESERVES THE FROZEN GRAMMAR'S MIRRORED SPECIAL CASES: transparency
  base inversion ("less transparent" raises the base), animation
  durations inversion ("faster" lowers the scale) — the same honest
  notes the parser emits, reused verbatim in spirit.
- EVERY routed request carries EVIDENCE (matched terms, synonyms,
  typo fixes, structural hits) and a CALIBRATED confidence — the user
  approves or rejects a visible reason, never a black box.

Verdicts: PLAN (validated ops ready), QUESTION (ambiguity to answer),
ABSTAIN, DELEGATE (another layer owns it: diagnose/search/brain/issue),
EXPLAIN, UNDO, LIST, INERT (scheme/wallpaper suggestions).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from ..settings import history as settings_history
from ..settings import planner as settings_planner
from ..settings import presets as settings_presets
from ..settings.cli import default_target
from ..settings.explain import ExplainError as SettingsExplainError
from ..settings.explain import explain as settings_explain
from ..settings.registry import ToolSpec, tool_by_name
from . import compound as compound_mod
from .compound import CompoundResult, route_compound
from .learn import CortexLearner
from .memory import new_episode
from .nlhistory import parse_query as parse_history_query
from .nlhistory import plan as plan_history
from .router import (
    AGENT_SEQ_RE,
    RouteResult,
    RouterState,
    DEFAULT_STATE,
    route,
)
from .session import SessionState, turn as session_turn

# Intensity modifiers scale the step count / multiply factor.
_INTENSITY_RE = re.compile(
    r"\b(?:much|a lot|way|significantly|seriously|heavily|drastically|max)\b"
)
_SOFT_RE = re.compile(r"\b(?:a bit|a little|slightly|tiny bit|barely|just a tad)\b")

# Transparency inversion (parser.py's TRANS_* semantics, mirrored): for
# the opacity BASE, "less transparent" means MORE base opacity.
_TRANS_DOWN_RE = re.compile(r"\b(?:more transparent|see\s*-?\s*through|translucent)\b")
_TRANS_UP_RE = re.compile(r"\b(?:less transparent|more opaque|more solid|less see\s*-?\s*through)\b")

_SCHEME_SUGGESTIONS = [
    "SUGGESTED_NOT_EXECUTED: caelestia scheme list",
    "SUGGESTED_NOT_EXECUTED: caelestia scheme set -n <name>",
]
_WALLPAPER_SUGGESTIONS = [
    "SUGGESTED_NOT_EXECUTED: caelestia wallpaper -f <path>",
    "SUGGESTED_NOT_EXECUTED: caelestia wallpaper -r (random)",
]


# Surfaces that are not shell.json tools: routing to any of these means
# the clause left the settings ontology (the same set the pipeline's
# delegate branch handles, plus the inert/terminal verdict surfaces).
_NON_TOOL_SURFACES = frozenset({
    "explain", "undo", "history", "scheme", "wallpaper",
    "diagnose", "search", "brain", "issue", "genius", "agent",
})


def agent_shaped(text: str, compound: CompoundResult) -> bool:
    """True when the request is a sequenced multi-step GOAL that crosses
    the settings boundary — the structural cue the agent delegate keys on.

    Two conditions, both required (the router's own cue-lexicon +
    structural-floor discipline, applied at full-text scope):

    - sequencing grammar: ``router.AGENT_SEQ_RE`` ("... then ...",
      "after that", "first ... then", "step by step") on the full text —
      the connective the compound splitter would otherwise shred is the
      signal that the ORDER of the clauses is part of the request;
    - boundary crossing: at least one clause the settings surface cannot
      turn into an op (ABSTAIN / no top candidate / routed to a
      non-tool surface such as genius or search).

    Pure settings sequences ("disable blur then make the dock smaller")
    keep their existing compound behavior: two ops, one composed plan,
    one confirmation gate. Sequencing + boundary crossing is exactly the
    shape the agent's simulated task graph exists for.
    """
    if compound.single:
        # A single clause keeps its sequencing vocabulary intact, so the
        # router's pattern boost already floors the agent surface — the
        # per-clause delegate branch below handles it.
        return False
    if not AGENT_SEQ_RE.search(text.lower()):
        return False
    for clause_route in compound.routes:
        top = clause_route.top
        if (top is None or clause_route.verdict == "ABSTAIN"
                or top.surface in _NON_TOOL_SURFACES):
            return True
    return False


# ---------------------------------------------------------------------------
# Cue -> op value resolution (the router's hints become planner ops).
# ---------------------------------------------------------------------------


def _step_count(cues: Dict[str, object], text: str) -> int:
    """Signed step count for relative ops: ±1 baseline, ±2 for intense
    modifiers ("much bigger"), and percentages become multiply factors."""
    direction = int(cues.get("direction", 0) or 0)
    if direction == 0:
        return 0
    magnitude = 1
    if _INTENSITY_RE.search(text.lower()):
        magnitude = 2
    elif _SOFT_RE.search(text.lower()):
        magnitude = 1
    return direction * magnitude


def _multiply_factor(cues: Dict[str, object], text: str) -> Optional[float]:
    """Percent cues become a multiply factor: "20% bigger" -> 1.2,
    "20% smaller" -> 0.8. Sign comes from the direction cue or the
    explicit +/- on the number itself."""
    percent = cues.get("percent")
    if percent is None:
        return None
    percent = float(percent)
    direction = int(cues.get("direction", 0) or 0)
    if direction == 0:
        direction = 1 if "-" not in str(percent) and _INTENSITY_RE.search(text.lower()) else 1
    factor = 1.0 + (direction * percent / 100.0)
    return round(factor, 4)


def ops_for_candidate(surface: str, cues: Dict[str, object], raw: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Turn one routed tool + its cues into planner-shaped ops.

    Returns (ops, notes). Notes carry every honest caveat (bool tools
    have no strength, string tools are not settable, enum values listed
    on ambiguity) — the same voice as parser.py's notes."""
    spec = tool_by_name(surface)
    if spec is None:
        return [], [f"'{surface}' is not a registry tool"]
    ops: List[Dict[str, Any]] = []
    notes: List[str] = []

    def op(action: str, value: Any, note: Optional[str] = None) -> None:
        row: Dict[str, Any] = {"tool": surface, "action": action, "value": value, "raw": raw}
        if note:
            row["note"] = note
        ops.append(row)

    kind = spec.kind
    lowered = raw.lower()

    if kind == "bool":
        if cues.get("bool") is True or cues.get("bool") is False:
            op("set", bool(cues["bool"]))
        elif cues.get("toggle"):
            op("set", "TOGGLE")  # resolved against the live file below
            notes.append("toggle resolved against the current value at plan time")
        elif cues.get("direction"):
            value = cues.get("direction") == 1
            notes.append(f"{surface.replace('set', '').lower()} is on/off only — "
                         f"{'enabling' if value else 'disabling'} it")
            op("set", value)
        else:
            notes.append(f"{surface}: on or off? (say 'enable/disable {surface.replace('set', '').lower()}')")

    elif kind in ("float", "int"):
        if cues.get("reset"):
            op("set", spec.default)
        elif cues.get("number") is not None and cues.get("percent") is None:
            op("set", cues["number"])
        elif cues.get("percent") is not None:
            factor = _multiply_factor(cues, raw)
            if factor is not None:
                op("multiply", factor)
        elif cues.get("absolute") is not None:
            target_value = float(cues["absolute"])
            if spec.minimum is not None and spec.maximum is not None:
                absolute_value = spec.minimum if target_value <= 0.5 else spec.maximum
                op("set", absolute_value)
                notes.append(f"absolute request -> range {'minimum' if target_value <= 0.5 else 'maximum'} ({absolute_value})")
            else:
                notes.append("no numeric range on this setting for an absolute request")
        else:
            steps = _step_count(cues, raw)
            # Transparency base inversion (mirrors parser.py's TRANS class).
            if spec.name == "setTransparencyBase":
                if _TRANS_UP_RE.search(lowered):
                    steps = abs(steps) or 1
                elif _TRANS_DOWN_RE.search(lowered):
                    steps = -(abs(steps) or 1)
                if steps:
                    notes.append("opacity base: lower = more transparent")
            if steps:
                op("step", steps)
            else:
                notes.append(f"{surface}: by how much? (a number, a percent like '20% smaller', "
                             f"or a direction like 'smaller')")

    elif kind == "enum":
        position = cues.get("position")
        if position is not None and spec.enum and position in [str(v).lower() for v in spec.enum]:
            for value in spec.enum:
                if str(value).lower() == position:
                    op("set", value)
                    break
        elif cues.get("reset"):
            op("set", spec.default)
        else:
            # literal enum value in the text?
            matched = False
            if spec.enum:
                for value in spec.enum:
                    text_value = str(value).lower().replace("_", " ")
                    if re.search(rf"\b{re.escape(text_value)}\b", lowered):
                        op("set", value)
                        matched = True
                        break
            if not matched:
                values = ", ".join(str(v) for v in (spec.enum or ())) or "n/a"
                notes.append(f"{surface}: which value? ({values})")

    elif kind == "string":
        notes.append(f"{surface} is a string setting (e.g. a font family); "
                     "string values are not parsed from free text — use --call")

    return ops, notes


def _resolve_toggle(plan_ops: List[Dict[str, Any]], file_path: Path) -> List[str]:
    """Resolve TOGGLE placeholders against the live file (read-only).
    A toggle on a missing file/section flips the registry default."""
    import json

    current: Dict[str, Any] = {}
    notes: List[str] = []
    if file_path.exists():
        try:
            loaded = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (OSError, ValueError):
            notes.append("could not read the target file for toggle resolution; using defaults")
    for op in plan_ops:
        if op.get("value") == "TOGGLE":
            spec = tool_by_name(op["tool"])
            if spec is None:
                continue
            node: Any = current
            for piece in spec.path.split("."):
                if isinstance(node, dict):
                    node = node.get(piece)
                else:
                    node = None
                    break
            old = node if node is not None else spec.default
            op["value"] = not bool(old)
            op["note"] = f"toggle: current value {old!r} -> {op['value']!r}"
    return notes


# ---------------------------------------------------------------------------
# The pipeline.
# ---------------------------------------------------------------------------


class CortexResult:
    """Rich result for one processed request (dict-shaped for --json)."""

    def __init__(self) -> None:
        self.verdict: str = "ABSTAIN"
        self.resolved_text: str = ""
        self.ops: List[Dict[str, Any]] = []
        self.plan: Optional[Dict[str, Any]] = None
        self.confidence: float = 0.0
        self.questions: List[str] = []
        self.notes: List[str] = []
        self.evidence: List[str] = []
        self.suggestions: List[str] = []
        self.delegate: Optional[str] = None
        self.explain_answer: Optional[Dict[str, Any]] = None
        self.history_plan: Optional[Dict[str, Any]] = None
        self.candidates: List[Dict[str, Any]] = []
        self.session_note: str = ""
        self.strategy: str = ""
        self.learn_hook: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "verdict": self.verdict,
            "resolved_text": self.resolved_text,
            "ops": self.ops,
            "confidence": self.confidence,
            "questions": self.questions,
            "notes": self.notes,
            "evidence": self.evidence,
            "candidates": self.candidates,
            "session_note": self.session_note,
            "strategy": self.strategy,
        }
        if self.plan is not None:
            out["plan"] = self.plan
        if self.suggestions:
            out["suggestions"] = self.suggestions
        if self.delegate:
            out["delegate"] = self.delegate
        if self.explain_answer is not None:
            out["explain"] = self.explain_answer
        if self.history_plan is not None:
            out["history_plan"] = self.history_plan
        if self.learn_hook is not None:
            out["learn_hook"] = self.learn_hook
        return out


def process(
    text: str,
    *,
    session: Optional[SessionState] = None,
    learner: Optional[CortexLearner] = None,
    file_path: Union[str, Path, None] = None,
    now: Optional[datetime] = None,
    router_state: Optional[RouterState] = None,
) -> CortexResult:
    """Process one natural-language request end-to-end (read-only).

    ``session``: live conversational state (anaphora/answers). When
    None, the request is treated as one-shot.
    ``learner``: when provided, the router uses the LEARNED state
    (strategy bandit + fitted weights) and the result carries the
    calibrated confidence + learn hook for the caller to report the
    outcome back after the user decides.
    """
    now = now or datetime(2026, 1, 1, 12, 0, 0)
    target = Path(file_path) if file_path else default_target()
    result = CortexResult()

    strategy = ""
    state = router_state
    if state is None and learner is not None:
        strategy, state = learner.choose_strategy()
    if state is None:
        state = DEFAULT_STATE

    # 1. Session resolution (anaphora / pending-question answers).
    resolved = text
    if session is not None:
        turn_result = session_turn(text, session, router_state=state)
        resolved = turn_result.resolved_text
        result.session_note = turn_result.note
        result.resolved_text = resolved
    else:
        result.resolved_text = text

    # 2. Compound split + per-clause routing.
    compound = route_compound(resolved, state=state)
    if compound.single and compound.routes and compound.routes[0].verdict == "ABSTAIN" and not compound.clauses:
        result.verdict = "ABSTAIN"
        result.questions.append(compound.routes[0].question or "no addressable request")
        return result

    # 2.5 Agent shape: a sequenced multi-step goal that crosses the settings
    # boundary delegates to the agent layer WHOLE — the per-clause splitter
    # would shred the sequence and half-address it. The agent answers with a
    # simulated task graph (consent stays a manual step, always).
    if agent_shaped(resolved, compound):
        result.verdict = "DELEGATE"
        result.delegate = "agent"
        result.resolved_text = resolved
        result.confidence = 0.0
        result.notes.append(
            "multi-step request across layers — the agent layer owns it "
            "(simulated plan only; nothing runs without your consent)")
        return result

    ops: List[Dict[str, Any]] = []
    questions: List[str] = []
    notes: List[str] = list(compound.notes)
    evidence: List[str] = []
    top_route: Optional[RouteResult] = None

    for clause, clause_route in zip(compound.clauses, compound.routes):
        top = clause_route.top
        if top is None:
            questions.append(f"{clause.text!r}: nothing matched")
            continue
        if top_route is None:
            top_route = clause_route
        evidence.extend(f"[{clause.text[:40]}] {e}" for e in top.evidence[:4])
        result.candidates.append({
            "clause": clause.text, "surface": top.surface, "kind": top.kind,
            "score": top.score, "p": top.p,
        })

        if clause.keep:
            notes.append(f"keep-clause honored (no change to {top.surface})")
            continue

        surface = top.surface
        if surface.startswith("preset:"):
            preset_name = surface.split(":", 1)[1]
            preset_ops = settings_presets.preset_ops(preset_name)
            ops.extend(preset_ops)
            notes.append(f"preset '{preset_name}': conservative defaults, review before applying")
        elif surface in ("scheme", "wallpaper"):
            result.suggestions.extend(_SCHEME_SUGGESTIONS if surface == "scheme" else _WALLPAPER_SUGGESTIONS)
            notes.append("this lives in the scheme/wallpaper system outside shell.json; "
                         "inert suggestions only")
        elif surface == "explain":
            try:
                answer = settings_explain(clause.text, target)
                result.explain_answer = answer
            except SettingsExplainError:
                # It looked like a why-question but names no registry
                # setting — the genius layer is the honest fallback for
                # universal questions, not a crash.
                result.delegate = "genius"
                notes.append("not a settings question — trying the genius layer")
        elif surface in ("undo", "history"):
            query = parse_history_query(clause.text, now=now)
            entries = settings_history.entries(target)
            history_plan = plan_history(query, entries, now=now)
            result.history_plan = {
                "verdict": history_plan.verdict, "action": history_plan.action,
                "steps": history_plan.steps, "entry_id": history_plan.entry_id,
                "reason": history_plan.reason,
                "entries": history_plan.entries, "total": history_plan.total_entries,
            }
        elif surface in ("diagnose", "search", "brain", "issue", "genius", "agent"):
            result.delegate = surface
            notes.append(f"this reads like a {surface} request — the {surface} layer owns it")
        else:
            clause_ops, clause_notes = ops_for_candidate(surface, top.cues, clause.text)
            ops.extend(clause_ops)
            notes.extend(f"[{clause.text[:40]}] {n}" for n in clause_notes)
            if clause_route.verdict == "AMBIGUOUS" and clause_route.question:
                questions.append(clause_route.question)

    # 3. Confidence (calibrated when a learner is attached).
    confidence = 0.0
    if top_route is not None and top_route.top is not None:
        confidence = top_route.top.p
        if learner is not None:
            confidence = learner.calibrated_confidence(top_route.top.p)
    result.confidence = round(confidence, 3)
    result.strategy = strategy
    result.evidence = evidence

    # 4. Terminal verdicts that need no plan.
    if result.explain_answer is not None:
        result.verdict = "EXPLAIN"
        result.notes = notes
        return result
    if result.history_plan is not None:
        result.verdict = "UNDO" if result.history_plan.get("action") else "LIST"
        result.notes = notes
        return result
    if result.delegate is not None:
        result.verdict = "DELEGATE"
        result.notes = notes
        return result
    if result.suggestions and not ops:
        result.verdict = "INERT"
        result.notes = notes
        return result

    # 5. Plan (validation happens in the existing planner, untouched).
    if not ops:
        if questions:
            result.verdict = "QUESTION"
            result.questions = questions
            result.notes = notes
            return result
        result.verdict = "ABSTAIN"
        result.questions.append("no addressable request")
        result.notes = notes
        return result

    # 4.2 ordering: dedupe same-tool clauses (last spoken wins) and apply
    # the declared precedence DAG so a mode toggle never lands after the
    # strength change of a subsystem it is switching off.
    ops, order_notes = compound_mod.order_ops(ops)
    notes.extend(order_notes)

    notes.extend(_resolve_toggle(ops, target))
    try:
        plan = settings_planner.plan(ops, target)
    except settings_planner.PlannerError as exc:
        result.verdict = "ABSTAIN"
        result.notes = notes + [f"planner refused: {exc}"]
        return result
    result.plan = plan
    result.ops = ops
    result.notes = notes
    result.questions = questions

    if plan.get("apply_blocked"):
        result.verdict = "QUESTION"
        if not questions:
            questions.append("the plan has validation errors (see plan.errors)")
    else:
        result.verdict = "PLAN"

    # 6. Learn hook: what the caller should report back after the user
    # decides (approve/apply -> positive, reject -> negative).
    if top_route is not None and top_route.top is not None and learner is not None:
        surface = top_route.top.surface
        features = top_route.features.get(surface, {})
        result.learn_hook = {
            "text": text[:120], "surface": surface,
            "features": features, "p": top_route.top.p,
        }
    return result


def episode_for(result: CortexResult, text: str, outcome: str,
                now: Optional[datetime] = None) -> Dict[str, Any]:
    """Build the memory episode for one processed request (the caller
    records it — the pipeline never writes state itself)."""
    surfaces = [c["surface"] for c in result.candidates]
    return new_episode(text, result.resolved_text, surfaces, result.verdict.lower(),
                       outcome, at=now or datetime(2026, 1, 1, 12, 0, 0))
