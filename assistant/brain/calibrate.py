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


def fold_undo_negatives(stats, undo_log, weight=1.0, kind="settings"):
    """A3 — fold the settings layer's PII-stripped undo log into the
    Beta-Binomial posteriors as EXPLICIT negative signal.

    ``stats`` is an acceptance_rate() result ({kind: {alpha, beta, mean, n}});
    ``undo_log`` is settings.history.undo_log(target) — records of
    {"tool", "magnitude", "direction"} and nothing else (the PII-strip
    rule; magnitude is retained for future weighting experiments and
    inspectability, not used to scale the evidence — an undo is one
    negative observation regardless of how big the reverted change was).

    Each record adds ``weight`` to the beta (negative) side of BOTH the
    kind-level posterior (``kind``, default "settings": a change the user
    reverted is evidence against settings proposals generally) and a
    per-tool posterior under ``"tool:<name>"`` (evidence against that
    specific knob). Means are recomputed; ``n`` counts folded records so
    the honesty invariant (an effective sample size you can see) holds.
    Mutates and returns ``stats`` (same dict, callers keep ownership).
    """
    for record in undo_log or []:
        tool = record.get("tool")
        if not tool:
            continue
        for key in (kind, f"tool:{tool}"):
            entry = stats.setdefault(
                key, {"alpha": 1.0, "beta": 1.0, "mean": 0.5, "n": 0})
            entry["beta"] += float(weight)
            entry["n"] += 1
            entry["mean"] = round(
                entry["alpha"] / (entry["alpha"] + entry["beta"]), 3)
    return stats


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
