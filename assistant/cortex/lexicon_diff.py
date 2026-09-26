"""cortex.lexicon_diff — federated, opt-in, signed lexicon-diff sharing
(phase 2.6, proposals/2026-09-26-c-lexicon-diff-sharing.md).

The shareable artifact is a plain-text, reviewable list of
``phrase -> tool`` mappings a user's cortex has learned (reroute
corrections + approved routes), capped at the newest 200, PII-stripped
to the undo log's standard: no timestamps, no file paths, no values —
phrases are the only content, and phrases are what the user chose to
type at the assistant.

Federation means reviewable text over the channels the community
already uses (issue threads, matrix, fork PRs) — NO server, NO
network code, NO crypto code in the assistant (the import allow-list
is untouched). "Signed" happens OUTSIDE: an Ed25519 detached signature
over the canonical diff text produced and verified by a tool the user
already trusts (minisign / sq / GPG); the assistant only states whose
corpus a diff claims to be — trust in that identity stays a human
decision.

The module is PURE (no I/O): the caller loads/saves the brain state.
State shape (new key, forward-compatible):

    state["lexicon_imports"] = {
        "<diff-id>": {
            "rows": [{"text", "surface", "n", "p", "label"}],
            "at": "2026-09-26T..."   # import time, local metadata only
        }, ...
    }

The diff-id is sha256[:12] of the canonical row text — `forget` drops
the set by id, restoring the pre-import pair list (and therefore the
corpus-only embedder build on the next process).

Import safety (the proposal's own mitigations, all pinned by test):
- import caps (200 rows);
- per-phrase length cap (120 chars, the learner's own bound);
- rows naming NON-EXISTENT tools import as no-ops with warnings,
  never exceptions (injection fuzz);
- the import report lists every tool the diff would boost;
- imports land as SUPERVISED PAIRS in the embedder seam (A2's
  ``labeled_pairs`` — never into the hand-seeded SYNONYMS, which stay
  a reviewed diff) and as review-bucket candidates for the learner's
  batch-review flow.

Embedder wiring (the one runtime consequence): PpmiEmbedder's shared
singleton (vectorize.embedder) reads the persisted pairs at its lazy
first build — an ABSENT import keeps the corpus-only build byte-for-
byte (the A2-measured default), which is why the fingerprint test in
test_svd_embedder pins the no-pairs build.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "DIFF_HEADER", "MAX_PAIRS", "PHRASE_MAX", "IMPORTS_KEY",
    "export_rows", "render", "parse", "diff_id", "import_diff",
    "forget", "persisted_pairs", "imported_ids",
]

DIFF_HEADER = "CAELESTIA LEXICON DIFF v1"
MAX_PAIRS = 200
PHRASE_MAX = 120
IMPORTS_KEY = "lexicon_imports"

_ROW_RE = re.compile(
    r"^\s*(?P<sign>[+-])(?P<text>.*?\S)\s*->\s*(?P<surface>\S+)"
    r"(?:\s*\(n=(?P<n>\d+),\s*p=(?P<p>[0-9.]+)\))?\s*$")
_DATE_RE = re.compile(r"^\((.+)\)\s*$")


# ---------------------------------------------------------------------------
# Export (the learner's examples -> reviewable rows).
# ---------------------------------------------------------------------------


def export_rows(state: Dict[str, Any], learn_key: str = "cortex_learn",
                max_pairs: int = MAX_PAIRS) -> List[Dict[str, Any]]:
    """Derive the shareable rows from the learner's bounded example log:
    group by (text, surface); n = occurrences; p = the mean ROUTE
    probability the user saw; the sign is the majority outcome
    (+ approved/applied, - corrected/rejected). Newest ``max_pairs``
    groups by last-seen position. PII-safe: only text/surface/n/p."""
    examples = []
    learn = state.get(learn_key)
    if isinstance(learn, dict):
        raw = learn.get("examples") or []
        examples = [dict(r) for r in raw if isinstance(r, dict)]
    order: Dict[Tuple[str, str], int] = {}
    agg: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for pos, row in enumerate(examples):
        text = str(row.get("text", ""))[:PHRASE_MAX].strip()
        surface = str(row.get("surface", "")).strip()
        if not text or not surface:
            continue
        key = (text, surface)
        if key not in agg:
            agg[key] = {"text": text, "surface": surface,
                        "n": 0, "p_sum": 0.0, "plus": 0, "minus": 0}
            order[key] = pos
        a = agg[key]
        a["n"] += 1
        try:
            a["p_sum"] += float(row.get("p", 0.0))
        except (TypeError, ValueError):
            pass
        if int(row.get("label", 0)) == 1:
            a["plus"] += 1
        else:
            a["minus"] += 1
    # newest groups last-seen first, cap, then deterministic order by text
    newest = sorted(order, key=lambda k: -order[k])[:max_pairs]
    rows = []
    for key in sorted(newest):
        a = agg[key]
        rows.append({
            "text": a["text"],
            "surface": a["surface"],
            "n": a["n"],
            "p": round(a["p_sum"] / a["n"], 2) if a["n"] else 0.0,
            "label": 1 if a["plus"] >= a["minus"] else 0,
        })
    return rows


def render(rows: List[Dict[str, Any]], date: str = "") -> str:
    """The canonical diff text — deterministic for the same rows (and
    the same date string; the CLI stamps today, tests pin a fixed one).
    Sorted by text; one row per line; nothing else in the artifact."""
    lines = [f"{DIFF_HEADER}  ({date})" if date else DIFF_HEADER]
    for row in sorted(rows, key=lambda r: (r.get("text", ""),
                                           r.get("surface", ""))):
        sign = "+" if int(row.get("label", 1)) == 1 else "-"
        n = int(row.get("n", 1))
        p = float(row.get("p", 0.0))
        lines.append(f"{sign}{row.get('text', '')} -> "
                     f"{row.get('surface', '')}  (n={n}, p={p:.2f})")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Parse + validate (never raises; malformed input is a warning).
# ---------------------------------------------------------------------------


def parse(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse a diff back into rows. Returns (rows, warnings). Malformed
    lines, over-long phrases, unknown tools, and over-cap rows become
    WARNINGS, never exceptions (the injection-fuzz contract)."""
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    known_tools: Optional[Dict[str, bool]] = None

    def _tool_exists(name: str) -> bool:
        nonlocal known_tools
        if known_tools is None:
            from ..settings.registry import TOOL_SPECS
            known_tools = {spec.name: True for spec in TOOL_SPECS}
        return name in known_tools

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped == DIFF_HEADER \
                or stripped.startswith(DIFF_HEADER) \
                or stripped.startswith("#"):
            continue  # header (with or without date) / blank / comment:
            # no-ops
        m = _ROW_RE.match(stripped)
        if not m:
            warnings.append(f"line {lineno}: unparseable, skipped: "
                            f"{stripped[:60]!r}")
            continue
        phrase = m.group("text").strip()
        surface = m.group("surface").strip()
        if len(phrase) > PHRASE_MAX:
            warnings.append(f"line {lineno}: phrase over {PHRASE_MAX} chars, "
                            "skipped (the learner's own bound)")
            continue
        if not _tool_exists(surface):
            warnings.append(f"line {lineno}: {surface!r} is not a registry "
                            "tool, skipped (unknown tools never import)")
            continue
        if any(r["text"] == phrase and r["surface"] == surface for r in rows):
            warnings.append(f"line {lineno}: duplicate row, skipped")
            continue
        rows.append({
            "text": phrase,
            "surface": surface,
            "n": max(1, int(m.group("n") or 1)),
            "p": min(1.0, max(0.0, float(m.group("p") or 0.0))),
            "label": 1 if m.group("sign") == "+" else 0,
        })
        if len(rows) > MAX_PAIRS:
            warnings.append(f"line {lineno}: over the {MAX_PAIRS}-row import "
                            "cap, skipped")
            rows.pop()
    return rows, warnings


def diff_id(rows: List[Dict[str, Any]]) -> str:
    """Stable id for one imported set: sha256[:12] of the canonical rows
    (id → same set; any row change → different id)."""
    canonical = render(sorted(rows, key=lambda r: (r.get("text", ""),
                                                   r.get("surface", ""))),
                       date="canonical")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Import / forget (state-transforming, still pure — caller persists).
# ---------------------------------------------------------------------------


def import_diff(state: Dict[str, Any], text: str) -> Dict[str, Any]:
    """Apply one diff into the state: parse + validate, persist the rows
    under their diff-id, and REPORT (boosted tools, parity measurement,
    rollback command). Never touches SYNONYMS; never raises on
    malformed input."""
    rows, warnings = parse(text)
    if not rows:
        return {"error": "nothing importable in this diff "
                         f"({len(warnings)} warning(s))",
                "warnings": warnings}
    did = diff_id(rows)
    imports = state.get(IMPORTS_KEY)
    if not isinstance(imports, dict):
        imports = {}
    imports[did] = {"rows": rows, "n": len(rows)}
    state[IMPORTS_KEY] = imports
    # review-bucket candidates (the proposal's second landing): each row
    # becomes one candidate the learner's batch-review flow can label —
    # imports are absorbed through the supervised path, never silently
    try:
        from . import learn as cortex_learn
        bucket = [dict(c) for c in state.get(cortex_learn.REVIEW_KEY, [])
                  if isinstance(c, dict)]
        known = {c.get("text") for c in bucket}
        from datetime import datetime
        stamped = datetime.now().isoformat()
        for row in rows:
            if row["text"] in known:
                continue  # already parked for review
            bucket.append({"text": row["text"], "verdict": "IMPORTED",
                           "surface": row["surface"], "p": row.get("p"),
                           "at": stamped})
        state[cortex_learn.REVIEW_KEY] = bucket[:cortex_learn.MAX_CANDIDATES]
    except Exception:
        pass  # the review-bucket landing is best-effort, never fatal
    # the boosted-tools warning (the injection surface made visible)
    boosted = sorted({row["surface"] for row in rows})
    return {
        "diff_id": did,
        "imported": len(rows),
        "boosted_tools": boosted,
        "warnings": warnings,
        "note": "the pairs weight the shared embedder at its next build "
                "(supervision, weight above the corpus prior — never the "
                "hand-seeded SYNONYMS); review candidates were added for "
                "the learner's batch flow",
        "rollback": f"cortex lexicon forget {did}",
        "verify": "verify the signature with YOUR external tool "
                  "(minisign/sq/gpg) before trusting the source — the "
                  "assistant states the content, the human owns the trust",
    }


def forget(state: Dict[str, Any], the_id: str) -> Dict[str, Any]:
    """Drop one imported set by diff-id. The pre-import pair list is
    restored by construction (the remaining imports stand); the next
    embedder build drops the forgotten pairs."""
    imports = state.get(IMPORTS_KEY)
    if not isinstance(imports, dict) or the_id not in imports:
        known = sorted(k for k in imports if isinstance(k, str)) \
            if isinstance(imports, dict) else []
        return {"error": f"no imported diff {the_id!r} "
                + (f"(have: {', '.join(known)})" if known else
                   "(nothing imported)")}
    dropped = imports.pop(the_id)
    if not imports:
        state.pop(IMPORTS_KEY, None)
    else:
        state[IMPORTS_KEY] = imports
    return {"forgot": the_id, "rows_dropped": len(dropped.get("rows", [])),
            "note": "the next embedder build drops these pairs "
                    "(corpus-only again for this set)"}


def imported_ids(state: Dict[str, Any]) -> List[str]:
    imports = state.get(IMPORTS_KEY)
    if not isinstance(imports, dict):
        return []
    return sorted(str(k) for k in imports)


def persisted_pairs(state: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Flatten the imported sets into supervised (text, surface) pairs
    for the embedder seam — the A2 ``labeled_pairs`` parameter."""
    pairs: List[Tuple[str, str]] = []
    imports = state.get(IMPORTS_KEY)
    if not isinstance(imports, dict):
        return pairs
    for rows in (v.get("rows") or [] for v in imports.values()
                 if isinstance(v, dict)):
        for row in rows:
            if isinstance(row, dict) and row.get("text") and row.get("surface"):
                pairs.append((str(row["text"]), str(row["surface"])))
    return pairs[:MAX_PAIRS]
