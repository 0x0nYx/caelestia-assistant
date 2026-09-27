"""personal.topics — NMF topic extraction over a markdown vault.

Lee & Seung 1999, "Learning the Parts of Objects by Non-Negative Matrix
Factorization", Nature 401, 788-791 — multiplicative-update NMF: a
non-negative docs-by-terms count matrix V is factorized as V ~= W H
(docs-by-k times k-by-terms) with every entry held >= 0, giving
additive parts-based topics ("each note is a non-negative mixture of
k topics") instead of the signed axes a singular-vector decomposition
would produce. The updates are the paper's alternating rules for the
squared-Euclidean objective (H *= (W^T V) / (W^T W H), then
W *= (V H^T) / (W H H^T)), which the paper proves monotone
non-increasing; nothing here is invented beyond the standard eps guard
in the denominators (zero-division protection, stated because the raw
alternative is 0/0).

COMPUTATION NOTES (they matter at vault scale): V is SPARSE (a note
holds few distinct terms), so the two V-touching products accumulate
over nonzeros only, and the reconstruction error is never materialized
densely — it uses the Frobenius identity ||V - WH||^2 = ||V||^2 -
2<V, WH> + sum_{t,t'} (W^T W)[t][t'] * (H H^T)[t][t'], whose pieces
are all k x k or sparse. Per-iteration cost is O(nnz(V) * k +
(n + m) * k^2), independent of the dense n*m matrix size.

HONESTY (what a topic report may and may not claim):

- NMF is a LOCAL optimizer: the factorization is not unique, and the
  topics converged to depend on the init. The init here is positive
  uniform draws from random.Random(seed) with a FIXED seed (default 0)
  — deterministic, stated, and pinned byte-identical by test — but a
  different seed is a different (equally valid) local optimum. The
  report therefore always carries iterations / converged / error, and
  the note says descriptive clusters, not discovered truth;
- converged means the updates became STATIONARY (relative error change
  below tol) — on factorizations whose true factors hold exact zeros
  (a perfectly separable corpus) the multiplicative tail approaches
  zero sublinearly, so the run can honestly report converged=False
  with a small, still-shrinking error; the error field, not the flag,
  carries the quality;
- k is caller-chosen; k < 1 or k > number of docs is refused (a topic
  per note is not a topic model), as are empty corpora and empty
  vocabularies;
- the relative error is ||V - WH||_F / ||V||_F — reported, never
  hidden, so a bad factorization cannot masquerade as structure.

Pure stdlib, no I/O beyond the caller-supplied notes dict; no network;
the only randomness is the documented seeded init.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple

from ..nlp import tokens

EPS = 1e-10
DEFAULT_ITERS = 300
DEFAULT_TOL = 1e-9
DEFAULT_MAX_TERMS = 2000

__all__ = ["term_matrix", "nmf", "extract"]


def term_matrix(notes: Dict[str, Dict[str, Any]],
                max_terms: int = DEFAULT_MAX_TERMS,
                ) -> Tuple[List[str], List[str], List[List[float]]]:
    """The docs-by-terms count matrix over a scanned vault: notes and
    terms in sorted order (deterministic), counts from the shared
    tokenizer (brain/nlp.tokens). The vocabulary is capped at
    ``max_terms`` by DOCUMENT FREQUENCY then term order (the standard
    IR bound; keeps the factorization cost tied to the corpus's real
    signal, not to pathological vocabularies) — the cap is reported by
    whoever surfaces the matrix, never silent here: ``extract`` puts
    the kept term count in its report."""
    docs = sorted(notes)
    df: Dict[str, int] = {}
    per_doc = []
    for rel in docs:
        counts: Dict[str, int] = {}
        for tok in tokens(notes[rel]["text"]):
            counts[tok] = counts.get(tok, 0) + 1
        per_doc.append(counts)
        for tok in counts:
            df[tok] = df.get(tok, 0) + 1
    terms = sorted(df)
    if len(terms) > max_terms:
        terms = sorted(
            sorted(terms, key=lambda t: (-df[t], t))[:max_terms])
    rows = [[float(counts.get(t, 0)) for t in terms]
            for counts in per_doc]
    return docs, terms, rows


def nmf(v: List[List[float]], k: int, iters: int = DEFAULT_ITERS,
        tol: float = DEFAULT_TOL, seed: int = 0) -> Dict[str, Any]:
    """Factorize the non-negative matrix v (n docs x m terms) as W
    (n x k) times H (k x m) via Lee & Seung 1999 multiplicative
    updates from a seeded positive init. Deterministic for fixed
    (v, k, iters, tol, seed). Returns {"W", "H", "iterations",
    "converged", "error"} where error is the RELATIVE Frobenius error
    ||v - WH||_F / ||v||_F of the final iterate (computed via the
    Frobenius identity, see the module docstring). Refusals: k < 1,
    k > n, empty matrix, empty vocabulary."""
    n = len(v)
    if n == 0:
        raise ValueError("the matrix is empty — nothing to factorize")
    if k < 1:
        raise ValueError(f"k must be >= 1 (got {k!r})")
    if k > n:
        raise ValueError(
            f"k={k} exceeds the {n} document row(s) — a topic per note "
            "is not a topic model; refusing rather than padding")
    m = len(v[0])
    if m == 0:
        raise ValueError("the vocabulary is empty — no terms to form "
                         "topics from")
    # sparse view of V: per doc {term_index: count}
    sparse = [{j: row[j] for j in range(m) if row[j] > 0} for row in v]
    base_sq = sum(c * c for doc in sparse for c in doc.values())

    rng = random.Random(seed)
    w = [[rng.uniform(0.05, 1.0) for _ in range(k)] for _ in range(n)]
    h = [[rng.uniform(0.05, 1.0) for _ in range(m)] for _ in range(k)]

    def _wtw() -> List[List[float]]:
        return [[sum(w[i][a] * w[i][b] for i in range(n))
                 for b in range(k)] for a in range(k)]

    def _hht() -> List[List[float]]:
        return [[sum(h[a][j] * h[b][j] for j in range(m))
                 for b in range(k)] for a in range(k)]

    error = float("inf")
    for it in range(1, iters + 1):
        # ---- H *= (W^T V) / (W^T W H + eps)
        num = [[0.0] * m for _ in range(k)]
        for i, doc in enumerate(sparse):
            wi = w[i]
            for j, c in doc.items():
                for t in range(k):
                    num[t][j] += wi[t] * c
        wtw = _wtw()
        for a in range(k):
            ha, na = h[a], num[a]
            wa = wtw[a]
            for j in range(m):
                den = 0.0
                for b in range(k):
                    den += wa[b] * h[b][j]
                ha[j] = ha[j] * (na[j] / (den + EPS))
        # ---- W *= (V H^T) / (W H H^T + eps)
        num2 = [[0.0] * k for _ in range(n)]
        for i, doc in enumerate(sparse):
            ni = num2[i]
            for j, c in doc.items():
                for t in range(k):
                    ni[t] += c * h[t][j]
        hht = _hht()
        for i in range(n):
            wi, ni = w[i], num2[i]
            den = [sum(wi[b] * hht[b][t] for b in range(k))
                   for t in range(k)]
            for t in range(k):
                wi[t] = wi[t] * (ni[t] / (den[t] + EPS))
        # ---- error via the Frobenius identity (never dense WH)
        wtw, hht = _wtw(), _hht()
        wh_sq = sum(wtw[a][b] * hht[a][b]
                    for a in range(k) for b in range(k))
        cross = 0.0
        for i, doc in enumerate(sparse):
            wi = w[i]
            for j, c in doc.items():
                s = 0.0
                for t in range(k):
                    s += wi[t] * h[t][j]
                cross += c * s
        e2 = base_sq - 2.0 * cross + wh_sq
        prev = error
        error = (max(e2, 0.0) ** 0.5) / ((base_sq ** 0.5) + EPS)
        if abs(prev - error) < tol * max(error, EPS):
            return {"W": w, "H": h, "iterations": it,
                    "converged": True, "error": error}
    return {"W": w, "H": h, "iterations": iters, "converged": False,
            "error": error}


def extract(notes: Dict[str, Dict[str, Any]], k: int = 3,
            terms_per_topic: int = 6,
            max_terms: int = DEFAULT_MAX_TERMS) -> Dict[str, Any]:
    """The topic report over a scanned vault: k NMF topics, each with
    its strongest terms, every note with its mixture and dominant
    topic, and the honesty fields (iterations / converged / error /
    vocabulary size). Refuses (ValueError, with the reason) on empty
    corpora, empty vocabularies, and k outside 1..len(notes)."""
    if not notes:
        raise ValueError("no notes — nothing to extract topics from")
    docs, terms, rows = term_matrix(notes, max_terms=max_terms)
    if not terms:
        raise ValueError("no terms across the vault — the tokenizer "
                         "found nothing to build topics from")
    if k > len(docs):
        raise ValueError(
            f"k={k} exceeds the {len(docs)} note(s) — a topic per note "
            "is not a topic model")
    result = nmf(rows, k)
    w, h = result["W"], result["H"]

    topics = []
    for ti in range(k):
        ranked = sorted(zip(terms, h[ti]), key=lambda p: (-p[1], p[0]))
        top = [(t, round(x, 6)) for t, x in ranked[:terms_per_topic]
               if x > 0]
        member_docs = []
        for di, rel in enumerate(docs):
            row = w[di]
            if sum(row) <= 0:
                continue
            best = max(range(k), key=lambda j: (row[j], -j))
            if best == ti:
                member_docs.append(rel)
        topics.append({"terms": top, "docs": member_docs})

    doc_topics: Dict[str, Dict[str, Any]] = {}
    for di, rel in enumerate(docs):
        row = w[di]
        total = sum(row)
        if total <= 0:
            doc_topics[rel] = {"dominant": None, "mixture": []}
            continue
        mixture = [round(x / total, 6) for x in row]
        best = max(range(k), key=lambda j: (row[j], -j))
        doc_topics[rel] = {"dominant": best, "mixture": mixture}

    return {
        "k": k,
        "docs": len(docs),
        "terms": len(terms),
        "terms_kept": len(terms),
        "topics": topics,
        "doc_topics": doc_topics,
        "iterations": result["iterations"],
        "converged": result["converged"],
        "relative_error": round(result["error"], 8),
        "note": "NMF topics are descriptive co-occurrence clusters from "
                "a seeded local optimum — not unique, not semantic "
                "truth; the error/converged fields say how well the "
                "k-topic mixture explains the counts",
    }
