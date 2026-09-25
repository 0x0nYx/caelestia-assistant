"""Suggest new wiki-links between notes that share meaning but aren't linked.

Adamic-Adar scores a candidate pair by shared *neighbours* in the existing
link graph, down-weighting hub neighbours that link to everything (a rare
shared connection is stronger evidence than a popular one). Pairs with no
shared neighbours yet — including a brand-new vault with no links at all —
fall back to shingle-Jaccard on note text via minhash.signature(), so
suggestions work from the very first note.
"""
import math

from .minhash import jaccard, signature


def _neighbours(graph):
    out = {n: set(graph.out.get(n, set())) for n in graph.nodes}
    for src, tgts in graph.out.items():
        for t in tgts:
            out.setdefault(t, set()).add(src)
    return out


def adamic_adar(graph, a, b):
    neigh = _neighbours(graph)
    common = neigh.get(a, set()) & neigh.get(b, set())
    if not common:
        return 0.0
    return sum(1.0 / math.log(len(neigh.get(c, set())) + 1.001) for c in common)


def suggest_links(graph, notes, top=10, min_jaccard=0.15):
    """notes: {id: text}. Returns [{"a", "b", "score", "via"}] sorted desc,
    via in {"shared_neighbours", "text_similarity"}. Skips pairs already
    linked in either direction.
    """
    ids = sorted(notes)
    sigs = {i: signature(notes[i]) for i in ids}
    scored = []
    for idx, a in enumerate(ids):
        for b in ids[idx + 1:]:
            if b in graph.out.get(a, set()) or a in graph.out.get(b, set()):
                continue
            aa = adamic_adar(graph, a, b)
            if aa > 0:
                scored.append({"a": a, "b": b, "score": round(aa, 3), "via": "shared_neighbours"})
            elif sigs[a] and sigs[b]:
                j = jaccard(sigs[a], sigs[b])
                if j >= min_jaccard:
                    scored.append({"a": a, "b": b, "score": round(j, 3), "via": "text_similarity"})
    return sorted(scored, key=lambda r: -r["score"])[:top]
