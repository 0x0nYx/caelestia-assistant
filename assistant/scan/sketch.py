"""scan.sketch — Count-Min, HyperLogLog, reservoir sampling, EWMA, Page-Hinkley.

Four classical stream structures, one module, all plain-data serialisable:

- `CountMinSketch`: point-query frequencies with the (epsilon, delta) bound —
  the estimate never UNDER-counts, and over-counts by at most eps*N with
  probability 1-delta. Width/depth derived from the requested bounds.
- `HyperLogLog`: distinct count with ~1.04/sqrt(m) standard error using
  hashlib registers and stochastic averaging (Flajolet et al. 2007).
- `Reservoir`: Vitter's algorithm R — a uniform sample of k items from a
  stream of unknown length in one pass.
- `EWMA` + `page_hinkley`: exponentially weighted rate tracking and the
  Page-Hinkley change detector (cumulative alarm over negative drifts) —
  the honest way to say "the error rate just changed" without a model.
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, List, Optional

__all__ = ["CountMinSketch", "HyperLogLog", "Reservoir", "EWMA",
           "page_hinkley"]


# ---------------------------------------------------------------------------
# Count-Min Sketch
# ---------------------------------------------------------------------------

class CountMinSketch:
    def __init__(self, epsilon: float = 0.002, delta: float = 0.001) -> None:
        if epsilon <= 0 or not (0.0 < delta < 1.0):
            raise ValueError("epsilon > 0 and 0 < delta < 1 required")
        self.width = max(8, int(math.ceil(math.e / epsilon)))
        self.depth = max(2, int(math.ceil(math.log(1.0 / delta))))
        self.counters = [[0] * self.width for _ in range(self.depth)]
        self.total = 0

    def _indices(self, item: str):
        for d in range(self.depth):
            h = hashlib.sha256(f"{d}:{item}".encode()).digest()
            yield d, int.from_bytes(h[:8], "big") % self.width

    def add(self, item: str, count: int = 1) -> None:
        self.total += count
        for d, w in self._indices(item):
            self.counters[d][w] += count

    def estimate(self, item: str) -> int:
        return min(self.counters[d][w] for d, w in self._indices(item))

    def top_candidates(self, candidates: List[str], k: int = 10) -> List[tuple]:
        """Point-query a SHORTLIST (candidates must come from the caller —
        a sketch cannot enumerate; honesty about that beats pretending)."""
        pairs = [(self.estimate(c), c) for c in candidates]
        pairs.sort(reverse=True)
        return pairs[:k]

    def to_dict(self) -> Dict[str, Any]:
        return {"width": self.width, "depth": self.depth,
                "counters": self.counters, "total": self.total}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CountMinSketch":
        cms = cls.__new__(cls)
        cms.width, cms.depth = d["width"], d["depth"]
        cms.counters = d["counters"]
        cms.total = d["total"]
        return cms


# ---------------------------------------------------------------------------
# HyperLogLog
# ---------------------------------------------------------------------------

class HyperLogLog:
    def __init__(self, precision: int = 12) -> None:
        if not (4 <= precision <= 16):
            raise ValueError("precision must be in [4, 16]")
        self.p = precision
        self.m = 1 << precision
        self.registers = [0] * self.m

    def _bucket_and_rho(self, item: str):
        h = int.from_bytes(hashlib.sha256(str(item).encode()).digest(), "big")
        bucket = h >> (256 - self.p)
        rest = h & ((1 << (256 - self.p)) - 1) or 1
        rho = 1
        while not (rest & (1 << (255 - self.p))) and rho < 256 - self.p:
            rest <<= 1
            rho += 1
        return bucket, rho

    def add(self, item: str) -> None:
        bucket, rho = self._bucket_and_rho(item)
        if rho > self.registers[bucket]:
            self.registers[bucket] = rho

    def count(self) -> float:
        m = self.m
        alpha = {
            16: 0.673, 32: 0.697, 64: 0.709,
        }.get(m, 0.7213 / (1.0 + 1.079 / m))
        Z = sum(2.0 ** -r for r in self.registers)
        estimate = alpha * m * m / Z
        zeros = self.registers.count(0)
        if estimate <= 2.5 * m and zeros:
            estimate = m * math.log(m / zeros)  # linear counting for tiny N
        return estimate

    def merge(self, other: "HyperLogLog") -> None:
        if other.m != self.m:
            raise ValueError("precision mismatch; cannot merge")
        self.registers = [max(a, b) for a, b in zip(self.registers, other.registers)]

    def to_dict(self) -> Dict[str, Any]:
        return {"p": self.p, "registers": self.registers}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HyperLogLog":
        hll = cls.__new__(cls)
        hll.p, hll.m = d["p"], 1 << d["p"]
        hll.registers = d["registers"]
        return hll


# ---------------------------------------------------------------------------
# Reservoir sampling (Vitter R)
# ---------------------------------------------------------------------------

class Reservoir:
    def __init__(self, k: int = 50, seed: int = 7) -> None:
        if k <= 0:
            raise ValueError("k must be positive")
        self.k = k
        self.n = 0
        self.sample: List[str] = []
        self._rng = random.Random(seed)

    def offer(self, item: str) -> None:
        self.n += 1
        if len(self.sample) < self.k:
            self.sample.append(item)
        else:
            j = self._rng.randint(0, self.n - 1)
            if j < self.k:
                self.sample[j] = item

    def to_dict(self) -> Dict[str, Any]:
        return {"k": self.k, "n": self.n, "sample": self.sample}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Reservoir":
        r = cls.__new__(cls)
        r.k, r.n, r.sample = d["k"], d["n"], d["sample"]
        r._rng = random.Random(0)
        return r


# ---------------------------------------------------------------------------
# EWMA + Page-Hinkley change detection
# ---------------------------------------------------------------------------

class EWMA:
    """Exponentially weighted moving average of a 0/1 (or any) stream."""

    def __init__(self, alpha: float = 0.05) -> None:
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha in (0, 1]")
        self.alpha = alpha
        self.mean: Optional[float] = None
        self.count = 0

    def update(self, value: float) -> float:
        if self.mean is None:
            self.mean = value
        else:
            self.mean = self.alpha * value + (1.0 - self.alpha) * self.mean
        self.count += 1
        return self.mean

    def to_dict(self) -> Dict[str, Any]:
        return {"alpha": self.alpha, "mean": self.mean, "count": self.count}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EWMA":
        e = cls.__new__(cls)
        e.alpha, e.mean, e.count = d["alpha"], d["mean"], d["count"]
        return e


def page_hinkley(values: List[float], threshold: float = 12.0,
                 alpha: float = 0.98, delta: float = 0.005,
                 min_instances: int = 30) -> Dict[str, Any]:
    """Page-Hinkley test for an upward mean change in a stream.

    Returns {"change_at": index or None, "magnitude": float} — change_at is
    the FIRST index where the cumulative PH statistic crossed `threshold`
    (with a warm-up of `min_instances`). Standard drift detector for the
    "did my acceptance rate / error rate just jump?" question. The running
    mean starts AT the first value (so a stream that is high from line one
    is not mistaken for a rise from zero) and tracks with an EMA(alpha).
    """
    if not values:
        return {"change_at": None, "magnitude": 0.0, "threshold": threshold}
    mean = values[0]
    sum_xt = 0.0
    min_ht = math.inf
    change_at: Optional[int] = None
    for i, x in enumerate(values):
        if i > 0:
            mean = alpha * mean + (1.0 - alpha) * x
        sum_xt += x - mean - delta
        min_ht = min(min_ht, sum_xt)
        if i >= min_instances and (sum_xt - min_ht) > threshold and change_at is None:
            change_at = i
    return {"change_at": change_at,
            "magnitude": (sum_xt - min_ht),
            "threshold": threshold}
