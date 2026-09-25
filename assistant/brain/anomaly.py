"""Behavioural signals: z-score anomalies, deferral flags, focus entropy."""
import math
from collections import Counter


def zscore(history, x):
    if len(history) < 2:
        return 0.0
    mean = sum(history) / len(history)
    var = sum((h - mean) ** 2 for h in history) / (len(history) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0 if x == mean else math.inf
    return (x - mean) / sd


def deferral_flag(defer_count, threshold=3):
    return defer_count >= threshold


def shannon_bits(labels):
    """Entropy of task-switch labels. High entropy = fragmented attention."""
    counts = Counter(labels)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts.values())
