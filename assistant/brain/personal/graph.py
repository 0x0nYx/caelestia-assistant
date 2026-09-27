"""Note link graph: PageRank, orphans, and label-propagation communities.

Deterministic: nodes are visited in sorted order and ties break to the smallest
label, so the same vault always yields the same clusters.

exponential-build-3 D adds two link-graph views alongside PageRank:
- HITS (Kleinberg 1999, "Authoritative Sources in a Hyperlinked
  Environment", JACM 46(5), 604-632) — hub/authority scores from
  mutually-reinforcing power iteration, L1-normalized each step,
  reported side by side with PageRank wherever both are surfaced;
- TIME-DECAY EDGE WEIGHTS (``decay_weights``): exponential half-life
  weighting of a note's links by the note's age, feedable into the
  weighted PageRank (and HITS) so "which notes matter NOW" can differ
  from "which notes matter all-time". Both default to the unweighted
  behavior when no weights are given.
"""
import os
import re
from collections import Counter

LINK = re.compile(r"\[\[([^\]|#]+)")

DEFAULT_HALF_LIFE_DAYS = 90.0


def links(text):
    return {m.strip().lower() for m in LINK.findall(text)}


def decay_weights(notes, now, half_life_days=DEFAULT_HALF_LIFE_DAYS):
    """Time-decay edge weights for a scanned vault: every wiki-link edge
    (source, target) carries ``2 ** (-age_days(source) / half_life_days)``
    — an exponential half-life on the SOURCE note's file age (a note
    edited today links at full strength; a note untouched for one
    half-life links at half strength). ``now`` is a caller-supplied
    epoch timestamp (fixture-injectable for determinism; pass
    ``datetime.now(timezone.utc).timestamp()`` in live code — the same
    injection pattern health_report uses). Read-only: touches nothing
    but mtime. Notes whose mtime cannot be read weigh as fresh (the
    same OSError convention as health_report). Pure function of
    (notes, now, half_life_days); ``half_life_days <= 0`` is refused.
    """
    if half_life_days <= 0:
        raise ValueError(
            f"half_life_days must be positive (got {half_life_days!r})")
    weights = {}
    for rel, note in notes.items():
        try:
            age_days = max(
                (float(now) - os.path.getmtime(note["path"])) / 86400.0,
                0.0)
        except OSError:
            age_days = 0.0
        weight = 2.0 ** (-age_days / half_life_days)
        for target in links(note["text"]):
            weights[(rel.lower(), target)] = weight
    return weights


class Graph:
    def __init__(self):
        self.out = {}

    def add(self, node, targets):
        self.out.setdefault(node, set()).update(targets)
        for t in targets:
            self.out.setdefault(t, set())

    @property
    def nodes(self):
        return sorted(self.out)

    def in_degree(self):
        deg = Counter()
        for src, tgts in self.out.items():
            for t in tgts:
                deg[t] += 1
        return deg

    def pagerank(self, damping=0.85, iters=50, weights=None):
        """PageRank with OPTIONAL edge-strength weights (exponential-
        build-3 D). Weights are EDGE STRENGTHS relative to an
        unweighted edge: 1.0 = full strength, values in (0, 1] (larger
        is refused — a weight can weaken an edge, never amplify it),
        so time-decay weights (which only shrink) fit exactly. The
        out-share of v is ``rank[v] * w(v, t) / len(out(v))`` — NOT
        renormalized by the weight sum, because per-source renormal-
        ization would cancel any per-source weighting (all of a
        source's edges decay together; normalizing them against each
        other hides the decay entirely — the flaw this formulation
        exists to avoid). The un-followed slack
        ``rank[v] * (1 - mean_weight(v))`` joins the dangling mass and
        teleports uniformly, so total rank stays 1: a stale note's
        links are followed with lower probability and the walker
        teleports instead — the time-aware random surfer. With
        ``weights=None`` (or all weights 1.0) this is byte-identical
        to the original implementation (pinned by test)."""
        nodes = self.nodes
        n = len(nodes)
        if n == 0:
            return {}
        if weights is not None:
            for (src, tgt), w in weights.items():
                if tgt in self.out.get(src, ()):
                    if w <= 0:
                        raise ValueError(
                            f"edge weight for ({src}, {tgt}) must be "
                            f"positive (got {w!r}); refusing rather "
                            "than clamping")
                    if w > 1.0:
                        raise ValueError(
                            f"edge weight for ({src}, {tgt}) exceeds "
                            f"full strength 1.0 (got {w!r}); weights "
                            "weaken edges (e.g. time decay), they "
                            "never amplify them")
        rank = {v: 1.0 / n for v in nodes}
        for _ in range(iters):
            dangling = sum(rank[v] for v in nodes if not self.out[v])
            new = {v: (1 - damping) / n + damping * dangling / n
                   for v in nodes}
            for v in nodes:
                if not self.out[v]:
                    continue
                out_v = self.out[v]
                if weights is None:
                    share = damping * rank[v] / len(out_v)
                    for t in out_v:
                        new[t] += share
                    continue
                per = [(t, weights.get((v, t), 1.0)) for t in out_v]
                strength = sum(w for _t, w in per) / len(per)
                for t, w in per:
                    new[t] += damping * rank[v] * w / len(per)
                slack = rank[v] * (1.0 - strength)
                if slack > 0:
                    # the un-followed share teleports uniformly
                    for t in new:
                        new[t] += damping * slack / n
            rank = new
        return rank

    def hits(self, max_iter=100, tol=1e-10, weights=None):
        """Kleinberg 1999, "Authoritative Sources in a Hyperlinked
        Environment", JACM 46(5), 604-632 — HITS: authorities are the
        notes good hubs point at; hubs are the notes that point at good
        authorities. Classic power iteration (auth = weighted sum of
        in-neighbors' hub scores, hub = weighted sum of out-neighbors'
        authority scores, L1-normalized each step, nodes visited in
        sorted order), with the same OPTIONAL positive edge weights as
        pagerank (e.g. time-decay; ``None`` = unweighted). Converged is
        an honest flag, not an assumption: it reports whether the
        hub+authority delta fell below ``tol`` within ``max_iter``.
        Returns {"hub", "authority", "iterations", "converged"}."""
        nodes = self.nodes
        if not nodes:
            return {"hub": {}, "authority": {}, "iterations": 0,
                    "converged": True}
        if weights is not None:
            for (src, tgt), w in weights.items():
                if tgt in self.out.get(src, ()):
                    if w <= 0:
                        raise ValueError(
                            f"edge weight for ({src}, {tgt}) must be "
                            f"positive (got {w!r}); refusing rather "
                            "than clamping")
                    if w > 1.0:
                        raise ValueError(
                            f"edge weight for ({src}, {tgt}) exceeds "
                            f"full strength 1.0 (got {w!r}); weights "
                            "weaken edges (e.g. time decay), they "
                            "never amplify them")
        incoming = {v: [] for v in nodes}
        for src in nodes:
            for t in self.out[src]:
                incoming[t].append(src)
        hub = {v: 1.0 / len(nodes) for v in nodes}
        auth = {v: 1.0 / len(nodes) for v in nodes}
        for it in range(1, max_iter + 1):
            new_auth = {
                v: sum(hub[u] * (1.0 if weights is None
                                 else weights.get((u, v), 1.0))
                       for u in incoming[v])
                for v in nodes}
            s = sum(new_auth.values())
            if s > 0:
                new_auth = {v: x / s for v, x in new_auth.items()}
            new_hub = {
                v: sum(new_auth[t] * (1.0 if weights is None
                                      else weights.get((v, t), 1.0))
                       for t in self.out[v])
                for v in nodes}
            s = sum(new_hub.values())
            if s > 0:
                new_hub = {v: x / s for v, x in new_hub.items()}
            delta = sum(abs(new_auth[v] - auth[v])
                        + abs(new_hub[v] - hub[v]) for v in nodes)
            auth, hub = new_auth, new_hub
            if delta < tol:
                return {"hub": hub, "authority": auth, "iterations": it,
                        "converged": True}
        return {"hub": hub, "authority": auth, "iterations": max_iter,
                "converged": False}

    def orphans(self):
        indeg = self.in_degree()
        return [v for v in self.nodes if not self.out[v] and indeg[v] == 0]

    def communities(self, max_iter=30):
        undirected = {v: set() for v in self.out}
        for src, tgts in self.out.items():
            for t in tgts:
                undirected[src].add(t)
                undirected[t].add(src)
        labels = {v: v for v in self.out}
        for _ in range(max_iter):
            changed = False
            for v in self.nodes:
                if not undirected[v]:
                    continue
                counts = Counter(labels[u] for u in undirected[v])
                best = max(counts.values())
                new = min(lbl for lbl, c in counts.items() if c == best)
                if new != labels[v]:
                    labels[v] = new
                    changed = True
            if not changed:
                break
        groups = {}
        for v, lbl in labels.items():
            groups.setdefault(lbl, []).append(v)
        return sorted((sorted(g) for g in groups.values()), key=lambda g: (-len(g), g[0]))
