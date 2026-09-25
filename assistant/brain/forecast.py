"""Holt linear-trend smoothing (forecast) and a 1-D Kalman filter (smoothing)."""


def holt(series, alpha=0.5, beta=0.3, horizon=7):
    if not series:
        return []
    if len(series) == 1:
        return [series[0]] * horizon
    level, trend = series[0], series[1] - series[0]
    for x in series[1:]:
        prev_level = level
        level = alpha * x + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return [level + (h + 1) * trend for h in range(horizon)]


class Kalman1D:
    """Random-walk model. q: process noise, r: measurement noise."""

    def __init__(self, q=0.01, r=0.5, x0=0.5, p0=1.0):
        self.q, self.r, self.x, self.p = q, r, x0, p0

    def update(self, z):
        self.p += self.q
        k = self.p / (self.p + self.r)
        self.x += k * (z - self.x)
        self.p *= (1 - k)
        return self.x
