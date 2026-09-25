"""Multi-intent clause splitting: one sentence, many settings.

parser.py deliberately refuses compound requests ("multiple value phrases
found in one request; split that into separate requests") because a
frozen grammar cannot attribute values to tools safely. The cortex
router can: each clause gets routed independently, and the pipeline
composes the per-clause plans into one multi-op proposal — which then
goes through the SAME multi-change confirmation gate (``--confirm`` /
ledger approval) that single-sentence multi-setting presets use.

Algorithm — deterministic clause segmentation:

1. Split on coordinating/contrastive conjunctions and commas OUTSIDE
   any protectable span. Splits happen only when BOTH sides carry
   addressable content (a noun hit, a direction/bool/position/number
   cue, or a non-stopword token count above threshold) — "blur and
   transparency" is one concept, "disable blur and move the bar up" is
   two intents.
2. Contrast scope: "but keep the blur on" / "except the dock" clauses
   are marked ``contrast`` so the pipeline treats them as
   negative-scoped (a request to NOT touch, or to restore, that thing)
   rather than a second change.
3. Each clause is routed via router.route; clause results are merged
   left-to-right (later clauses win conflicts, mirroring how humans
   read "make it bigger but the dock smaller").

PURE module: no I/O, no randomness. Deterministic for identical input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .router import RouteResult, RouterState, DEFAULT_STATE, route

# Split points: coordinating conjunctions, additive adverbs, commas,
# semicolons, and "then" sequencing. Contrast markers are recorded but
# flagged (the clause is a modifier of intent, not a new one).
_SPLIT_RE = re.compile(
    r"\s+(?:and|also|plus|then|after that|while you're at it)\s+|[,;]\s+"
)
_CONTRAST_SPLIT_RE = re.compile(r"\s+(?:but|except|however|although|instead)\s+")
# Contrast clauses often carry a keep/leave verb phrase — protected from
# being misread as a change request when composed.
_CONTRAST_KEEP_RE = re.compile(
    r"\b(?:keep|leave|stay|maintain|don'?t (?:touch|change|move)|do not (?:touch|change|move))\b",
    re.IGNORECASE,
)

# A clause must carry at least one addressable signal to be routable on
# its own: a cue, or this many non-stopword tokens.
_MIN_CONTENT_TOKENS = 1

# Words that make a clause a follow-up modifier rather than an intent:
# "a bit smaller", "a little more", "same for the dock".
_MODIFIER_RE = re.compile(r"^\s*(?:a\s+(?:bit|little|tad|touch)|same(?:\s+for|\s+too|\s+with)|me\s+too|also)\b", re.IGNORECASE)


@dataclass
class Clause:
    """One split-out piece of the original request."""

    text: str                    # clause text, stripped, lowercased
    contrast: bool               # True when introduced by but/except/...
    keep: bool                   # True when the clause says "keep/leave X"
    position: int                # clause order index (0-based)


@dataclass
class CompoundResult:
    """Routed clauses plus composition guidance."""

    clauses: List[Clause] = field(default_factory=list)
    routes: List[RouteResult] = field(default_factory=list)
    single: bool = True          # True when no split happened
    notes: List[str] = field(default_factory=list)


def _has_content(clause_text: str) -> bool:
    """A clause carries content when it yields any router cue or at
    least one non-stopword token (routing will score it regardless; this
    is the cheap pre-filter that prevents conjunction-shredding of
    single concepts like "blur and transparency")."""
    from .router import extract_cues  # local import avoids a cycle at import time

    cues = extract_cues(clause_text)
    if cues:
        return True
    from .vectorize import tokenize

    return len(tokenize(clause_text)) >= _MIN_CONTENT_TOKENS


def split_clauses(text: str) -> List[Clause]:
    """Deterministic clause segmentation with content guards.

    Contrast markers (but/except/...) split too, but the right-hand
    clause is flagged; if it is a keep-phrase it is marked ``keep`` and
    routed like any clause (the router will find the tool; the pipeline
    turns keep-clauses into no-op/restore notes instead of changes).
    """
    raw = text.strip()
    if not raw:
        return []
    lowered = raw.lower()

    # First split on contrast markers (they subsume coordination for
    # scoping purposes), then on plain coordination within each side.
    spans: List[Tuple[str, bool]] = []
    last = 0
    for match in _CONTRAST_SPLIT_RE.finditer(lowered):
        spans.append((lowered[last:match.start()], False))
        last = match.end()
        # the contrast clause runs until the next contrast marker or end
        nxt = _CONTRAST_SPLIT_RE.search(lowered, last)
        end = nxt.start() if nxt else len(lowered)
        spans.append((lowered[last:end], True))
        last = end
    spans.append((lowered[last:], False))

    clauses: List[Clause] = []
    for chunk, is_contrast in spans:
        pieces = _SPLIT_RE.split(chunk) if not is_contrast else [chunk]
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            if not _has_content(piece):
                continue
            clauses.append(Clause(
                text=piece,
                contrast=is_contrast,
                keep=bool(_CONTRAST_KEEP_RE.search(piece)),
                position=len(clauses),
            ))
    # A single trailing modifier clause ("... and a bit smaller") folds
    # back into the previous clause — it modifies, not adds.
    if len(clauses) >= 2 and _MODIFIER_RE.match(clauses[-1].text) and not clauses[-1].contrast:
        merged = f"{clauses[-2].text} {clauses[-1].text}"
        clauses = clauses[:-2] + [Clause(merged, clauses[-2].contrast, clauses[-2].keep, clauses[-2].position)]
    return clauses


def route_compound(text: str, state: RouterState = DEFAULT_STATE, k: int = 3) -> CompoundResult:
    """Split, then route each clause. Single-intent input collapses to a
    one-clause result with ``single=True`` (identical behavior to plain
    ``router.route`` on the whole text — the split is a no-op)."""
    clauses = split_clauses(text)
    if not clauses:
        return CompoundResult(single=True, notes=["nothing addressable in the request"])
    if len(clauses) == 1:
        return CompoundResult(
            clauses=clauses,
            routes=[route(clauses[0].text, state=state, k=k)],
            single=True,
        )
    routes = [route(c.text, state=state, k=k) for c in clauses]
    notes: List[str] = []
    kept = [c.text for c in clauses if c.keep]
    if kept:
        notes.append("keep-clauses are honored as do-not-touch, not changes: " + "; ".join(kept))
    return CompoundResult(clauses=clauses, routes=routes, single=False, notes=notes)
