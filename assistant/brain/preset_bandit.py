"""Thompson sampling over named arms: which settings presets/tools does this
user actually approve when the brain proposes them?

This is HourBandit's algorithm (bandit.py) generalised from a fixed 0-23
index to arbitrary string arms, because settings proposals are keyed by
preset name (or tool name), not by hour. Each arm is a Beta(alpha, beta):
an approval in the ledger is a success, a rejection is a failure. New arms
start at Beta(1, 1) -- a flat prior, i.e. "no opinion yet" -- so a preset
nobody has been offered before is neither favoured nor penalised.

Secondary reward (issue #120 Phase 3.2, optional): reward() accepts an
optional ``secondary`` signal in [0, 1] (0.5 neutral) computed from a
battery-drain-rate delta measured around the preset's active window (see
diagnostics/telemetry.py::reward_from_drain). It contributes fractional
pseudo-counts scaled by SECONDARY_REWARD_WEIGHT (default 0.25), so even a
max-strength secondary signal can never outweigh one real approve/reject
decision (+/-1.0). It is ADDITIVE context, never a replacement: with
secondary=None the update is byte-for-byte the original +/-1 reward.

This module never decides anything by itself: it only ranks candidates for
a human to choose from (settings_bridge.recommend), exactly like every
other brain learner. Persisted as a plain {name: [alpha, beta]} dict, same
shape as HourBandit.to_dict(), so it lives in the same state.json file.
"""
import random

SECONDARY_REWARD_WEIGHT = 0.25


class NamedBandit:
    def __init__(self, arms=None):
        # arms: {name: [alpha, beta]}
        self.arms = {k: [float(v[0]), float(v[1])] for k, v in (arms or {}).items()}

    def _arm(self, name):
        return self.arms.setdefault(name, [1.0, 1.0])

    def reward(self, name, approved, secondary=None):
        """One decision. ``approved`` is the primary +/-1 signal;
        ``secondary`` (optional, [0, 1], 0.5 neutral) folds in fractional
        pseudo-counts at SECONDARY_REWARD_WEIGHT strength."""
        alpha, beta = self._arm(name)
        if approved:
            alpha, beta = alpha + 1.0, beta
        else:
            alpha, beta = alpha, beta + 1.0
        if secondary is not None:
            r = min(1.0, max(0.0, float(secondary)))
            alpha += SECONDARY_REWARD_WEIGHT * r
            beta += SECONDARY_REWARD_WEIGHT * (1.0 - r)
        self.arms[name] = [alpha, beta]

    def sample(self, name, rng=None):
        rng = rng or random
        alpha, beta = self._arm(name)
        return rng.betavariate(alpha, beta)

    def rank(self, names, rng=None):
        """Candidates ranked by one Thompson draw each, best first.

        Returns [(name, draw, mean_estimate), ...]. mean_estimate
        (alpha / (alpha + beta)) is the stable, non-random summary shown to
        the human; ``draw`` is what decided the order, so exploration still
        surfaces under-tried arms occasionally.
        """
        rng = rng or random
        scored = []
        for name in names:
            alpha, beta = self._arm(name)
            draw = rng.betavariate(alpha, beta)
            scored.append((name, round(draw, 3), round(alpha / (alpha + beta), 3)))
        return sorted(scored, key=lambda row: -row[1])

    def to_dict(self):
        return {k: list(v) for k, v in self.arms.items()}

    @classmethod
    def from_dict(cls, d):
        return cls(d or {})
