"""Keyword extraction (TF-IDF) and extractive summarization (TextRank).

Both work with no external model: TF-IDF ranks a note's own distinctive words
against a corpus of other notes, and TextRank scores each sentence by how
much vocabulary it shares with the note's other sentences, run through the
same power-iteration idea as graph.Graph.pagerank but over a weighted
similarity matrix instead of wiki-links.
"""
import math
import re
from collections import Counter

from .nlp import tokens

SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _tf(doc_tokens):
    c = Counter(doc_tokens)
    total = sum(c.values()) or 1
    return {w: n / total for w, n in c.items()}


def keywords(text, corpus_texts=(), top=8):
    """Rank `text`'s own words by TF-IDF against corpus_texts (other notes,
    NOT including `text` itself). With no corpus, falls back to raw frequency.
    """
    doc_tokens = tokens(text)
    if not doc_tokens:
        return []
    tf = _tf(doc_tokens)
    other_docs = [tokens(t) for t in corpus_texts]
    n_docs = len(other_docs) + 1
    scored = []
    for w, f in tf.items():
        df = 1 + sum(1 for d in other_docs if w in d)
        idf = math.log(n_docs / df) + 1.0
        scored.append((w, f * idf))
    scored.sort(key=lambda x: -x[1])
    return [w for w, _ in scored[:top]]


def _sentences(text):
    text = text.strip()
    if not text:
        return []
    return [s.strip() for s in SENTENCE.split(text) if s.strip()]


def _similarity(a_tokens, b_tokens):
    a, b = set(a_tokens), set(b_tokens)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    norm = math.log(len(a) + 1) + math.log(len(b) + 1)
    return inter / norm if norm else 0.0


def summarize(text, sentences_out=3, damping=0.85, iters=40):
    """Extractive summary: the `sentences_out` highest-PageRank sentences, in
    their original order. Returns fewer sentences than that if the note is
    already shorter than the target.
    """
    sents = _sentences(text)
    n = len(sents)
    if n <= sentences_out:
        return sents
    tok = [tokens(s) for s in sents]
    weights = [[_similarity(tok[i], tok[j]) if i != j else 0.0 for j in range(n)]
               for i in range(n)]
    out_sum = [sum(row) or 1.0 for row in weights]
    rank = [1.0 / n] * n
    for _ in range(iters):
        new = [(1 - damping) / n] * n
        for j in range(n):
            for i in range(n):
                if weights[i][j]:
                    new[j] += damping * rank[i] * weights[i][j] / out_sum[i]
        rank = new
    top_idx = sorted(range(n), key=lambda i: -rank[i])[:sentences_out]
    return [sents[i] for i in sorted(top_idx)]
