"""genius.synth — tiny inductive program synthesis over string examples.

FlashFill-style trace-based synthesis (Gulwani 2011, "Automatically
Generating Program Transformations", PLDI 2011 / "Automating string
processing in spreadsheets using input-output examples", POPL 2011 —
the 2-3-example regime FlashFill was built for): from 2 or 3
(user-supplied) before/after string examples, induce ONE transformation
from a deliberately tiny DSL and render it — never execute anything.

The DSL (explainability over coverage, on purpose — every construct has
a plain-English rendering):
- a program is 1..3 STAGES joined by CONSTANT strings (possibly empty);
- each stage extracts from the before-string of the example with one of:
    prefix(i, d, k)  text before the k-th occurrence of delimiter d
    suffix(i, d, k)  text after the k-th occurrence of delimiter d
    between(i, d1, k1, d2, k2)  the text after the k1-th d1 and before
                     the k2-th d2 (occurrence indices 1, 2, or -1 = last)
    head(i, n) / tail(i, n)     the first / last n characters
- delimiters are the non-alphanumeric characters already present in the
  examples (ranked by frequency, capped at 5) — nothing is invented.

The inductive check (the honesty core): a candidate program must
reproduce EVERY example EXACTLY, and the joiner constants must be
identical across all examples; anything the DSL cannot explain is an
explicit ABSTAIN ("not guessable from these examples in this DSL") —
the same refuse-don't-clamp discipline as everywhere else. Multiple
consistent programs are reported as ambiguous (count included); the
returned one is the canonical first (fewest stages, then enumeration
order), and the ambiguity is never hidden.

Output safety: the transformation's application to new strings is pure
text computation. When the user supplies real target names, the module
renders `SUGGESTED_NOT_EXECUTED:` mv lines (risk tier STATE_CHANGING)
— inert strings the user copies and runs themselves, exactly the
troubleshooting layers' convention. Nothing here touches the
filesystem, spawns, or executes: pure string algebra, deterministic,
no RNG, no I/O.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = ["SynthError", "synthesize", "apply_program", "render",
           "suggest_renames"]

MAX_STAGES = 3
MIN_EXAMPLES = 2
MAX_EXAMPLES = 3
_MAX_DELIMS = 5
_MAX_OCC = 3          # occurrence indices 1, 2, -1
_MAX_HEADTAIL = 8


class SynthError(ValueError):
    """Raised for abstentions and malformed requests (the caller renders
    the reason; nothing is guessed)."""


# ---------------------------------------------------------------------------
# Expression enumeration and evaluation.
# ---------------------------------------------------------------------------

def _delims(samples: Sequence[str]) -> List[str]:
    """Non-alphanumeric characters present in the examples — whitespace
    included, it separates fields like any other character — ranked by
    total frequency (deterministic: frequency desc, then codepoint)."""
    counts: Dict[str, int] = {}
    for s in samples:
        for ch in s:
            if not ch.isalnum():
                counts[ch] = counts.get(ch, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [ch for ch, _n in ranked[:_MAX_DELIMS]]


def _occurrences(s: str, d: str) -> List[int]:
    out: List[int] = []
    start = 0
    while len(out) < _MAX_OCC:
        idx = s.find(d, start)
        if idx == -1:
            break
        out.append(idx)
        start = idx + len(d)
    return out


def _nth_occ(s: str, d: str, k: int) -> Optional[int]:
    """Position where the k-th occurrence of d starts (k 1-based; -1 =
    last). None when the occurrence does not exist."""
    occs = _occurrences(s, d)
    if k == -1:
        return occs[-1] if occs else None
    if 1 <= k <= len(occs):
        return occs[k - 1]
    return None


def _eval_expr(expr: Dict[str, Any], inputs: Sequence[str]) -> str:
    """Evaluate one stage expression against the inputs. A missing
    delimiter/occurrence yields "" — the candidate simply fails to
    explain anything non-empty (verification does the rest)."""
    kind = expr["kind"]
    i = int(expr.get("input", 1)) - 1
    if not (0 <= i < len(inputs)):
        return ""
    s = inputs[i]
    if kind == "head":
        return s[:max(0, int(expr["n"]))]
    if kind == "tail":
        n = max(0, int(expr["n"]))
        return s[len(s) - n:] if n <= len(s) else s
    d1 = str(expr.get("d1", ""))
    k1 = int(expr.get("k1", 1))
    p1 = _nth_occ(s, d1, k1)
    if p1 is None:
        return ""
    if kind == "prefix":
        return s[:p1]
    if kind == "suffix":
        return s[p1 + len(d1):]
    if kind == "between":
        d2 = str(expr.get("d2", ""))
        k2 = int(expr.get("k2", 1))
        p2 = _nth_occ(s, d2, k2)
        if p2 is None or p2 <= p1:
            return ""
        return s[p1 + len(d1):p2]
    return ""


def _exprs_for_input(idx: int, sample: str,
                     delims: Sequence[str]) -> List[Dict[str, Any]]:
    """Canonical enumeration order for one input's expressions."""
    out: List[Dict[str, Any]] = []
    for d in delims:
        for k in (1, 2, -1):
            out.append({"kind": "prefix", "input": idx, "d1": d, "k1": k})
            out.append({"kind": "suffix", "input": idx, "d1": d, "k1": k})
    for d1 in delims:
        for k1 in (1, 2, -1):
            for d2 in delims:
                for k2 in (1, 2, -1):
                    if d1 == d2 and k1 == k2:
                        continue
                    out.append({"kind": "between", "input": idx,
                                "d1": d1, "k1": k1, "d2": d2, "k2": k2})
    for n in range(1, min(_MAX_HEADTAIL, len(sample)) + 1):
        out.append({"kind": "head", "input": idx, "n": n})
        out.append({"kind": "tail", "input": idx, "n": n})
    return out


def _explainable_pieces(inputs_per_example: Sequence[Sequence[str]],
                        out: str,
                        delims: Sequence[str]
                        ) -> List[Tuple[Dict[str, Any], int]]:
    """(expr, length) candidates whose value for example 1 is a NON-EMPTY
    substring of example 1's output — the prefilter that keeps the
    join-enumeration tiny. Returns them with their example-1 value."""
    pieces: List[Tuple[Dict[str, Any], int]] = []
    inputs = inputs_per_example[0]
    for idx, s in enumerate(inputs, start=1):
        for expr in _exprs_for_input(idx, s, delims):
            v = _eval_expr(expr, inputs)
            if v and v in out:
                pieces.append((expr, len(v)))
    return pieces


def _stage_values(expr: Dict[str, Any],
                  inputs_per_example: Sequence[Sequence[str]]
                  ) -> List[str]:
    """The expression's value for EVERY example. Empty values are kept —
    a delimiter legitimately absent from one example's before-string
    extracts "" there while the output's joiner carries the character
    (the exact-match verification decides consistency, not this)."""
    return [_eval_expr(expr, inputs) for inputs in inputs_per_example]


# ---------------------------------------------------------------------------
# Synthesis.
# ---------------------------------------------------------------------------

def synthesize(examples: Sequence[Tuple[str, str]]) -> Dict[str, Any]:
    """Induce ONE transformation from 2-3 before/after examples.

    Returns {"program": ..., "rendered": ..., "checked": n,
             "alternatives": k, "ambiguous": bool}. Raises SynthError
    (an honest ABSTAIN) when the request is malformed or the DSL cannot
    explain the examples."""
    pairs = [(str(a), str(b)) for a, b in examples]
    if not (MIN_EXAMPLES <= len(pairs) <= MAX_EXAMPLES):
        raise SynthError(
            f"synthesis needs exactly {MIN_EXAMPLES}-{MAX_EXAMPLES} "
            f"before/after examples (got {len(pairs)}); fewer cannot "
            "induce, more is outside this tool's contract")
    ins = [a for a, _b in pairs]
    outs = [b for _a, b in pairs]
    if any(not a or not b for a, b in pairs):
        raise SynthError("empty before/after strings carry no signal")
    delims = _delims(ins + outs)
    # one BEFORE-string per example (the expr schema keeps an input
    # index for forward compatibility, but this API supervises exactly
    # one input column — v1)
    inputs_per_example = [[pairs[j][0]] for j in range(len(pairs))]

    # piece candidates, shared across stage counts (prefiltered on
    # example 1's output; later examples verify exactly)
    pieces = _explainable_pieces(inputs_per_example, outs[0], delims)

    def values(expr: Dict[str, Any]) -> Optional[List[str]]:
        return _stage_values(expr, inputs_per_example)

    candidates: List[Tuple[int, List[List[str]], List[str],
                            List[Dict[str, Any]]]] = []
    # m stages, m = 1..3: canonical order (fewest stages first)
    for m in range(1, MAX_STAGES + 1):
        usable = [(e, values(e)) for e, _ln in pieces]
        if m == 1:
            for e, vals in usable:
                if all(v == out for v, out in zip(vals, outs)):
                    candidates.append((1, [vals], [], [e]))
        elif m == 2:
            for (ea, va), (eb, vb) in ((x, y) for x in usable for y in usable):
                # example 1 fixes the joiner; consistency is exact equality
                a1, b1 = va[0], vb[0]
                if len(a1) + len(b1) > len(outs[0]):
                    continue
                j1 = outs[0][len(a1):len(outs[0]) - len(b1)]
                if a1 + j1 + b1 != outs[0]:
                    continue
                if all(va[j] + j1 + vb[j] == outs[j]
                       for j in range(1, len(outs))):
                    candidates.append((2, [va, vb], [j1], [ea, eb]))
        else:  # m == 3
            for (ea, va), (eb, vb), (ec, vc) in (
                    (x, y, z) for x in usable for y in usable
                    for z in usable):
                a1, b1, c1 = va[0], vb[0], vc[0]
                fixed = len(a1) + len(b1) + len(c1)
                if fixed > len(outs[0]):
                    continue
                # structural prune on example 1: the output must start
                # with a1, end with c1, and hold b1 in the middle region
                if (not outs[0].startswith(a1)
                        or not outs[0].endswith(c1)):
                    continue
                middle = outs[0][len(a1):len(outs[0]) - len(c1)]
                if b1 not in middle:
                    continue
                remainder = len(outs[0]) - fixed
                # split the remainder between the two joiners
                for take in range(remainder + 1):
                    j1 = outs[0][len(a1):len(a1) + take]
                    j2 = outs[0][len(a1) + take + len(b1):
                                 len(a1) + take + len(b1) + (remainder - take)]
                    if a1 + j1 + b1 + j2 + c1 != outs[0]:
                        continue
                    if all(va[j] + j1 + vb[j] + j2 + vc[j] == outs[j]
                           for j in range(1, len(outs))):
                        candidates.append((3, [va, vb, vc], [j1, j2],
                                           [ea, eb, ec]))
        if candidates:
            break  # canonical: the fewest consistent stage count wins

    if not candidates:
        raise SynthError(
            "no transformation in this DSL reproduces every example — "
            "abstaining, not guessing (try examples that share a "
            "delimiter pattern)")
    program_parts, joiners, exprs = candidates[0][1], candidates[0][2], \
        candidates[0][3]
    program = {"stages": exprs, "joiners": joiners}
    return {"program": program,
            "rendered": render(program),
            "checked": len(pairs),
            "alternatives": max(0, len(candidates) - 1),
            "ambiguous": len(candidates) > 1}


def apply_program(program: Dict[str, Any], inputs: Sequence[str]) -> str:
    """Apply the learned transformation to new input strings (pure text
    computation; the same expression evaluator training used). Refuses
    (never silently empties) when the program reads an input that was
    not supplied — an honest error, never a fabricated string."""
    stages = program.get("stages") or []
    joiners = program.get("joiners") or []
    if not stages:
        raise SynthError("no program to apply")
    supplied = len(inputs)
    needed = max(int(e.get("input", 1)) for e in stages)
    if needed > supplied:
        raise SynthError(
            f"the learned program reads input {needed} but only "
            f"{supplied} input string(s) were supplied — refusing to "
            "invent the missing part")
    vals = [_eval_expr(e, [str(s) for s in inputs]) for e in stages]
    acc = vals[0]
    for m in range(1, len(vals)):
        acc += (joiners[m - 1] if m - 1 < len(joiners) else "") + vals[m]
    return acc


# ---------------------------------------------------------------------------
# Rendering (every construct keeps its plain-English form).
# ---------------------------------------------------------------------------

_OCC_WORD = {1: "1st", 2: "2nd", -1: "last"}


def _render_expr(expr: Dict[str, Any]) -> str:
    i = int(expr.get("input", 1))
    kind = expr["kind"]
    d1 = expr.get("d1", "")
    k1 = int(expr.get("k1", 1))
    pos = _OCC_WORD.get(k1, f"{k1}th")
    if kind == "prefix":
        return f"text before the {pos} {d1!r} of input {i}"
    if kind == "suffix":
        return f"text after the {pos} {d1!r} of input {i}"
    if kind == "between":
        d2 = expr.get("d2", "")
        k2 = int(expr.get("k2", 1))
        pos2 = _OCC_WORD.get(k2, f"{k2}th")
        return (f"text between the {pos} {d1!r} and the {pos2} {d2!r} "
                f"of input {i}")
    if kind == "head":
        return f"the first {expr['n']} character(s) of input {i}"
    return f"the last {expr['n']} character(s) of input {i}"


def render(program: Dict[str, Any]) -> str:
    stages = program.get("stages") or []
    joiners = program.get("joiners") or []
    parts = [_render_expr(e) for e in stages]
    out = parts[0]
    for m in range(1, len(parts)):
        out += f"  +  {joiners[m - 1]!r}  +  " + parts[m]
    return out


def _shell_quote(s: str) -> str:
    return "'" + str(s).replace("'", "'\"'\"'") + "'"


def suggest_renames(program: Dict[str, Any],
                    names: Sequence[str]) -> List[str]:
    """Inert, copy-paste-ready mv lines (STATE_CHANGING tier) pairing
    each given name with the program's output for it. NEVER executed —
    the prefix is the whole contract; `mv -n` never clobbers."""
    lines: List[str] = []
    for name in names:
        new = apply_program(program, [name])
        if new == name:
            continue  # a no-op rename is not a suggestion
        lines.append(f"SUGGESTED_NOT_EXECUTED: [STATE_CHANGING] "
                     f"mv -n -- {_shell_quote(name)} {_shell_quote(new)}")
    return lines
