"""Learn how much to trust each proposal *kind*, and how many proposals to
show per day, from ledger history alone — no model, just Beta-Binomial
bookkeeping over decisions that already happened.

acceptance_rate: a posterior per kind, so a kind the user always rejects
stops being pushed as hard. confidence_calibration: the same bucket-vs-hit-
rate idea as journal.calibration_curve, but sourced from the ledger's own
stated confidence instead of a manually kept journal. DailyBudget: a
two-armed Beta bandit ("more" vs "less" proposals today) driven by whether
the user actually engaged, reusing bandit.HourBandit's Thompson-sampling
pattern for a different decision.
"""
import random
from collections import defaultdict


def acceptance_rate(labeled, prior_alpha=1.0, prior_beta=1.0):
    """labeled: [{"kind", "status"}], status in {"approved", "rejected"}
    (this is exactly Ledger.labeled()'s shape). Returns
    {kind: {"alpha", "beta", "mean", "n"}}.
    """
    stats = defaultdict(lambda: {"alpha": prior_alpha, "beta": prior_beta, "n": 0})
    for item in labeled:
        s = stats[item["kind"]]
        s["n"] += 1
        if item["status"] == "approved":
            s["alpha"] += 1.0
        else:
            s["beta"] += 1.0
    for s in stats.values():
        s["mean"] = round(s["alpha"] / (s["alpha"] + s["beta"]), 3)
    return dict(stats)


def confidence_calibration(labeled, bins=5):
    """labeled: [{"confidence", "status"}]."""
    buckets = defaultdict(list)
    for item in labeled:
        b = min(int(item["confidence"] * bins), bins - 1)
        buckets[b].append(item)
    out = []
    for b in sorted(buckets):
        items = buckets[b]
        avg_conf = sum(i["confidence"] for i in items) / len(items)
        hit = sum(1 for i in items if i["status"] == "approved") / len(items)
        out.append({"bucket": b, "n": len(items),
                    "avg_confidence": round(avg_conf, 3), "approval_rate": round(hit, 3)})
    return out


class DailyBudget:
    """Two arms, "more" and "less" proposals today. Reward = 1 if the user
    engaged (approved or rejected outright) rather than leaving it pending
    long enough to count as ignored."""

    def __init__(self, alpha=None, beta=None):
        self.alpha = dict(alpha) if alpha else {"more": 1.0, "less": 1.0}
        self.beta = dict(beta) if beta else {"more": 1.0, "less": 1.0}

    def choose(self, rng=None):
        rng = rng or random
        return max(self.alpha, key=lambda arm: rng.betavariate(self.alpha[arm], self.beta[arm]))

    def reward(self, arm, engaged):
        if engaged:
            self.alpha[arm] += 1.0
        else:
            self.beta[arm] += 1.0

    def to_dict(self):
        return {"alpha": self.alpha, "beta": self.beta}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("alpha"), d.get("beta"))
