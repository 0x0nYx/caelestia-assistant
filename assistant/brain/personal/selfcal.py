"""personal.selfcal — a Brier-score ledger over the user's own STATED
predictions.

The gap: brain/calibrate.py calibrates the ASSISTANT's routing
confidence; journal.py scores recorded DECISIONS. Neither captures the
thing people actually get wrong on their own: forward-looking
predictions they SAY out loud ("I'll finish the migration by Friday",
"70% chance this launch slips"). This module is the personal-only
ledger for exactly that — same bookkeeping shape as those two, a
distinct instance with its own state key, its own opt-in lifecycle and
none of their state touched (calibrate.py is NOT modified here).

OPT-IN, EXPLICIT LOGGING ONLY: a prediction exists because the user
recorded it — nothing is inferred from unstated behavior, note text,
task activity or any other side channel. The only signal this module
ever sees is what the user wrote down via predict()/resolve().

Scoring: the Brier score (Brier 1950, "Verification of forecasts
expressed in terms of probability", Monthly Weather Review 78) over
resolved predictions — mean squared error between the stated
probability and the binary outcome — plus a small-sample calibration
curve (fewer/wider bins than a reliability diagram, the same honesty
rule journal.py uses: a personal log is small).

Mirrors brain/calibrate.py's pattern (a plain-dict ledger the caller
persists through state.py) while being a separate, personal-only
instance. Pure functions; no I/O; no write path of its own.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

__all__ = ["STATE_KEY", "predict", "resolve", "brier_score",
           "calibration_curve", "open_predictions", "summary"]

STATE_KEY = "personal_predictions"

_FRAMING = ("your stated predictions, scored by Brier 1950's proper "
            "rule — a diary, not a judgement; lower is better, 0.25 is "
            "chance-level guessing")


def predict(entries: Dict[str, Dict[str, Any]], prediction_id: str,
            statement: str, probability: float,
            due: Optional[str] = None, at: Optional[str] = None
            ) -> Dict[str, Any]:
    """Record one STATED prediction (explicit logging only).

    ``probability`` must lie strictly inside (0, 1) — a prediction of
    "certain" is not a prediction; rejected, never clamped (the
    settings layer's convention). Mutates and returns the entry (the
    caller persists via state.py — no I/O here)."""
    p = float(probability)
    if not (0.0 < p < 1.0):
        raise ValueError(
            f"probability must be strictly inside (0, 1), got {probability} "
            "(a certainty claim is not a prediction — rejected, never "
            "clamped)")
    entries[prediction_id] = {
        "statement": statement,
        "p": p,
        "due": due,
        "at": at,
        "outcome": None,
        "resolved_at": None,
    }
    return entries[prediction_id]


def resolve(entries: Dict[str, Dict[str, Any]], prediction_id: str,
            happened: bool, resolved_at: Optional[str] = None
            ) -> Dict[str, Any]:
    """Record what actually happened for one prediction. Resolving an
    already-resolved entry is refused (the ledger keeps its first
    resolution — rewriting history would flatter the score)."""
    if prediction_id not in entries:
        raise KeyError(f"no prediction {prediction_id}")
    entry = entries[prediction_id]
    if entry["outcome"] is not None:
        raise ValueError(
            f"prediction {prediction_id} already resolved — the ledger "
            "keeps its first resolution")
    entry["outcome"] = bool(happened)
    entry["resolved_at"] = resolved_at
    return entry


def brier_score(entries: Dict[str, Dict[str, Any]]) -> Optional[float]:
    """Mean (p - outcome)^2 over RESOLVED predictions; None when nothing
    has resolved yet (no invented scores)."""
    resolved = [e for e in entries.values() if e["outcome"] is not None]
    if not resolved:
        return None
    return sum((e["p"] - (1.0 if e["outcome"] else 0.0)) ** 2
               for e in resolved) / len(resolved)


def calibration_curve(entries: Dict[str, Dict[str, Any]], bins: int = 5
                      ) -> List[Dict[str, Any]]:
    """Stated probability bucket vs actual hit rate over resolved
    predictions (fewer/wider bins than a reliability diagram — a
    personal log is small; journal.py's own rule)."""
    resolved = [e for e in entries.values() if e["outcome"] is not None]
    if not resolved:
        return []
    buckets: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for e in resolved:
        b = min(int(e["p"] * bins), bins - 1)
        buckets[b].append(e)
    out = []
    for b in sorted(buckets):
        items = buckets[b]
        avg_p = sum(e["p"] for e in items) / len(items)
        hit_rate = sum(1 for e in items if e["outcome"]) / len(items)
        out.append({"bucket": b, "n": len(items),
                    "avg_p": round(avg_p, 3),
                    "hit_rate": round(hit_rate, 3)})
    return out


def open_predictions(entries: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The still-unresolved statements (the honest to-review list)."""
    return [dict(e, id=k) for k, e in sorted(entries.items())
            if e["outcome"] is None]


def summary(entries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """One card: the Brier score, the calibration curve, the open count
    and the framing."""
    return {
        "brier": brier_score(entries),
        "calibration": calibration_curve(entries),
        "open": len(open_predictions(entries)),
        "resolved": sum(1 for e in entries.values()
                        if e["outcome"] is not None),
        "framing": _FRAMING,
    }
