"""One 0-100 health score per note, combining three existing signals —
staleness (survival), orphan status (graph), and duplication (minhash) —
into a single ranking instead of reading three separate reports to find
what needs attention.
"""
from .survival import completion_prob


def score(note_id, age_days, orphan_ids, dup_ids, survival_curve=None, horizon=30):
    """Returns {"id", "score", "stale", "orphan", "duplicate"}. Starts at 100
    and subtracts penalties; higher is healthier.

    survival_curve: output of survival.kaplan_meier over comparable notes'
    (age, "was revisited") history. Pass None if you don't track revisits
    yet — falls back to a plain age threshold.
    """
    s = 100.0
    is_orphan = note_id in orphan_ids
    is_dup = note_id in dup_ids
    if survival_curve is not None:
        p_revisit = completion_prob(survival_curve, age_days, horizon=horizon)
        stale = p_revisit < 0.1
        s -= (1.0 - p_revisit) * 40.0
    else:
        stale = age_days > 90
        s -= min(age_days / 90.0, 1.0) * 30.0
    if is_orphan:
        s -= 25.0
    if is_dup:
        s -= 15.0
    return {"id": note_id, "score": round(max(s, 0.0), 1),
            "stale": stale, "orphan": is_orphan, "duplicate": is_dup}


def rank_notes(notes_meta):
    """notes_meta: [dict as returned by score()]. Worst health first."""
    return sorted(notes_meta, key=lambda r: r["score"])
