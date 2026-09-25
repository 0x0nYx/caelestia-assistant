"""Duration estimates per task category, Bayesian in log-space.

Task durations are right-skewed, so we model log(minutes) as normal. A weak
prior (PRIOR_N pseudo-observations at 30 min) keeps the first estimates sane,
and each observed actual pulls the posterior toward your real behaviour.
"""
import math

PRIOR_N = 3
PRIOR_MU = math.log(30)
SD_FLOOR = 0.15
Z80 = 0.8416


class DurationModel:
    def __init__(self, cats=None):
        self.cats = dict(cats or {})

    def observe(self, category, minutes):
        c = self.cats.setdefault(category, {"n": 0, "sum": 0.0, "sumsq": 0.0})
        lm = math.log(max(minutes, 1.0))
        c["n"] += 1
        c["sum"] += lm
        c["sumsq"] += lm * lm

    def estimate(self, category):
        c = self.cats.get(category, {"n": 0, "sum": 0.0, "sumsq": 0.0})
        n = c["n"]
        mu = (PRIOR_N * PRIOR_MU + c["sum"]) / (PRIOR_N + n)
        sd = SD_FLOOR
        if n >= 2:
            mean = c["sum"] / n
            var = max(c["sumsq"] / n - mean * mean, 0.0)
            sd = max(math.sqrt(var), SD_FLOOR)
        return {"category": category, "n": n,
                "median_min": round(math.exp(mu), 1),
                "p80_min": round(math.exp(mu + Z80 * sd), 1)}
