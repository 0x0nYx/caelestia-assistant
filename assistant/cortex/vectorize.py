"""Lean semantic vectorization for the cortex router.

Two classical engines, both deterministic, both stdlib-only:

1. ``TfidfIndex`` — an Okapi BM25+ index (with the lower-bound ``delta``
   that keeps long documents from saturating) over the synthetic corpus
   documents. This is the LEXICAL half of the router's score: exact and
   stemmed word overlap between the user's phrase and each surface's
   document.

2. ``PpmiEmbedder`` — distributional word vectors: PPMI co-occurrence
   matrix (positive pointwise mutual information) reduced by sparse
   random projection (Achlioptas' {-1, 0, +1} matrix, the
   Johnson-Lindenstrauss guarantee that pairwise distances survive the
   reduction), then row-normalized. A text embeds as the sublinear-tf
   weighted average of its word vectors. This is the SEMANTIC half: it
   puts user vocabulary and registry vocabulary that co-occur in the
   same phrase-doc pairs near each other in cosine space, so "make it
   see-through-ish" lands near the transparency tools without anyone
   hand-listing that synonym.

This is deliberately the "poor man's word2vec" — explicit, auditable
arithmetic replacing a neural embedding. It cannot hallucinate: a word
absent from the corpus has a zero vector and contributes nothing.

Determinism: the projection matrix is drawn from ``random.Random(seed)``
with a FIXED default seed, so every build of the same corpus produces
bit-identical vectors. No clock, no os randomness, no I/O.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple

from .corpus import Row, all_rows, tool_documents
from .lexicon import stem

# ---------------------------------------------------------------------------
# Tokenization shared by both engines (stemmed, stopworded).
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "a", "an", "the", "my", "me", "i", "please", "could", "would", "can",
    "to", "of", "for", "and", "or", "but", "with", "at", "by", "in", "on",
    "is", "are", "was", "be", "been", "am", "do", "does", "did", "so",
    "just", "like", "want", "wants", "need", "needs", "it", "its", "this",
    "that", "these", "those", "there", "here", "you", "your", "up", "out",
    "make", "makes", "making", "set", "sets", "setting", "get", "gets",
    "change", "changes", "changing", "adjust", "adjusts", "turn", "turns",
    "put", "puts", "give", "gives", "apply", "applies", "bit", "little",
    "slightly", "somewhat", "more", "most", "less", "least", "much",
    "look", "looks", "feel", "feels", "feeling", "everything", "keep",
    "keeps", "overall", "style", "vibe", "stuff", "thing", "things",
    "too", "very", "really", "kind", "sort", "now", "then", "still",
    "see", "through", "move", "moves", "moving", "want", "wanted",
})

_MINUS_STOP = frozenset({"it", "that", "this", "them", "those"})  # pronouns session.py resolves


def tokenize(text: str, keep_pronouns: bool = False) -> List[str]:
    """Stemmed, stopword-filtered word list. Pronouns are normally
    dropped here (they carry no target information); ``session.py``
    re-injects resolved ones itself, so it passes keep_pronouns=True."""
    raw = [w for w in text.lower().replace("-", " ").split() if w]
    out: List[str] = []
    for w in raw:
        if not w.isalpha() and not w.isdigit():
            w = "".join(ch for ch in w if ch.isalpha())
            if not w:
                continue
        if not keep_pronouns and w in _MINUS_STOP:
            continue
        if w in _STOPWORDS and not (keep_pronouns and w in _MINUS_STOP):
            continue
        s = stem(w)
        if s and (s not in _STOPWORDS or (keep_pronouns and s in _MINUS_STOP)):
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# BM25+ lexical index.
# ---------------------------------------------------------------------------


class TfidfIndex:
    """Okapi BM25+ (k1=1.5, b=0.75, delta=1.0) over {key: document}.

    Pure in-memory, built once per process from the synthetic corpus.
    ``score`` returns the BM25+ sum for one query against one key —
    the standard lexical retrieval baseline, delta-smoothed so a long
    tool document never fully saturates its term weights.
    """

    def __init__(self, documents: Dict[str, str], k1: float = 1.5,
                 b: float = 0.75, delta: float = 1.0) -> None:
        self.k1 = k1
        self.b = b
        self.delta = delta
        self.doc_tokens: Dict[str, List[str]] = {
            key: tokenize(doc) for key, doc in documents.items()
        }
        self.doc_len = {key: max(1, len(toks)) for key, toks in self.doc_tokens.items()}
        self.avg_len = sum(self.doc_len.values()) / max(1, len(self.doc_len))
        self.df: Counter = Counter()
        for toks in self.doc_tokens.values():
            self.df.update(set(toks))
        self.n_docs = len(self.doc_tokens)

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0)

    def score(self, query_tokens: Sequence[str], key: str) -> float:
        toks = self.doc_tokens.get(key)
        if not toks:
            return 0.0
        tf = Counter(toks)
        dl = self.doc_len[key]
        norm = self.k1 * (1.0 - self.b + self.b * dl / self.avg_len)
        total = 0.0
        for term in query_tokens:
            f = tf.get(term, 0)
            if f == 0:
                continue
            idf = self._idf(term)
            total += idf * (f * (self.k1 + 1.0)) / (f + norm) + self.delta * (1.0 if f > 0 else 0.0)
        return total

    def search(self, text: str, keys: Iterable[str], k: int = 10) -> List[Tuple[str, float]]:
        """Top-k (key, score) by BM25+ — deterministic tie-break by key."""
        q = tokenize(text)
        scored = [(self.score(q, key), key) for key in keys]
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [(key, score) for score, key in scored[:k] if score > 0.0]


# ---------------------------------------------------------------------------
# PPMI + random-projection embedder.
# ---------------------------------------------------------------------------


class PpmiEmbedder:
    """Distributional word vectors via PPMI + Achlioptas random projection.

    Co-occurrence counts are gathered from the synthetic corpus in two
    modes (both deterministic):

    - phrase-internal: adjacent word pairs inside each row's text
      (window 1, both orders) — teaches word similarity;
    - phrase-to-document: every phrase word paired with every word of
      its surface's document — teaches user-word to registry-word
      proximity, which is what the router actually needs.

    The PPMI matrix is then multiplied by a sparse {-1,0,+1} projection
    of width ``dim`` (entries drawn with probability 1/6, 2/3, 1/6,
    scaled by 1/sqrt(dim)) and each word's projected row is L2-normalized.
    """

    def __init__(self, dim: int = 64, seed: int = 0x20260925) -> None:
        self.dim = dim
        self.seed = seed
        self._build()

    # -- construction -------------------------------------------------------

    def _build(self) -> None:
        rows = all_rows()
        docs = tool_documents()
        pair_counts: Counter = Counter()
        word_counts: Counter = Counter()
        total = 0

        def _count_pair(a: str, b: str) -> None:
            nonlocal total
            if a == b:
                return
            pair_counts[(a, b)] += 1
            pair_counts[(b, a)] += 1
            total += 2

        for row in rows:
            toks = tokenize(row.text, keep_pronouns=True)
            for a, b in zip(toks, toks[1:]):
                _count_pair(a, b)
            doc = docs.get(row.surface)
            if doc is None:
                # coarse surfaces: their own text is the document
                doc = row.text
            doc_toks = tokenize(doc)
            for a in toks:
                for b in doc_toks:
                    _count_pair(a, b)
            word_counts.update(set(toks))
            word_counts.update(set(doc_toks))

        # PPMI matrix as sparse dict-of-Counters.
        self.vocab = sorted(word_counts)
        self.index = {w: i for i, w in enumerate(self.vocab)}
        grand = max(1, total)
        ppmi: List[Dict[int, float]] = [dict() for _ in self.vocab]
        for (a, b), count in pair_counts.items():
            ia, ib = self.index.get(a), self.index.get(b)
            if ia is None or ib is None:
                continue
            p_ab = count / grand
            p_a = word_counts[a] / grand * 2.0  # symmetric counting doubles marginals
            p_b = word_counts[b] / grand * 2.0
            denom = p_a * p_b
            if denom <= 0:
                continue
            pmi = math.log(p_ab / denom)
            if pmi > 0:
                ppmi[ia][ib] = pmi

        # Achlioptas sparse random projection, seeded — deterministic.
        rng = random.Random(self.seed)
        scale = 1.0 / math.sqrt(self.dim)
        vectors: List[List[float]] = []
        for i in range(len(self.vocab)):
            vec = [0.0] * self.dim
            for j, val in ppmi[i].items():
                # one projection column set per (word,col) drawn on demand
                for col in range(self.dim):
                    r = rng.random()
                    if r < 1.0 / 6.0:
                        vec[col] += val * scale
                    elif r < 2.0 / 6.0:
                        vec[col] -= val * scale
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        self.vectors = vectors

    # -- querying -----------------------------------------------------------

    def word_vector(self, word: str) -> List[float]:
        i = self.index.get(stem(word))
        return self.vectors[i] if i is not None else [0.0] * self.dim

    def embed(self, text: str, keep_pronouns: bool = False) -> List[float]:
        """Sublinear-tf weighted average of word vectors (tf weight
        ``1 + log(tf)``). Unknown words contribute exactly nothing."""
        toks = tokenize(text, keep_pronouns=keep_pronouns)
        counts = Counter(toks)
        vec = [0.0] * self.dim
        mass = 0.0
        for word, tf in counts.items():
            i = self.index.get(word)
            if i is None:
                continue
            weight = 1.0 + math.log(tf)
            wv = self.vectors[i]
            for col in range(self.dim):
                vec[col] += weight * wv[col]
            mass += weight
        if mass > 0:
            vec = [v / mass for v in vec]
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    @staticmethod
    def cosine(a: Sequence[float], b: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na > 0 and nb > 0 else 0.0

    def similarity(self, text_a: str, text_b: str) -> float:
        return self.cosine(self.embed(text_a), self.embed(text_b))


# ---------------------------------------------------------------------------
# Process-wide singletons (built once, deterministic, cheap: ~300 docs).
# ---------------------------------------------------------------------------

_INDEX: TfidfIndex | None = None
_EMBEDDER: PpmiEmbedder | None = None


def index() -> TfidfIndex:
    """The shared BM25+ index over tool documents + surface rows."""
    global _INDEX
    if _INDEX is None:
        documents = tool_documents()
        for row in all_rows():
            documents.setdefault(f"row::{row.text}", row.text)
        _INDEX = TfidfIndex(documents)
    return _INDEX


def embedder() -> PpmiEmbedder:
    """The shared PPMI embedder (fixed seed)."""
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = PpmiEmbedder()
    return _EMBEDDER
