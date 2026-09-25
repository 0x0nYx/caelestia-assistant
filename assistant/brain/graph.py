"""Note link graph: PageRank, orphans, and label-propagation communities.

Deterministic: nodes are visited in sorted order and ties break to the smallest
label, so the same vault always yields the same clusters.
"""
import re
from collections import Counter

LINK = re.compile(r"\[\[([^\]|#]+)")


def links(text):
    return {m.strip().lower() for m in LINK.findall(text)}


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

    def pagerank(self, damping=0.85, iters=50):
        nodes = self.nodes
        n = len(nodes)
        if n == 0:
            return {}
        rank = {v: 1.0 / n for v in nodes}
        for _ in range(iters):
            dangling = sum(rank[v] for v in nodes if not self.out[v])
            new = {v: (1 - damping) / n + damping * dangling / n for v in nodes}
            for v in nodes:
                if self.out[v]:
                    share = damping * rank[v] / len(self.out[v])
                    for t in self.out[v]:
                        new[t] += share
            rank = new
        return rank

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
