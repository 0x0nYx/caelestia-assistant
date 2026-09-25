"""Brain service layer: every operation as a function returning plain data.

The CLI (cli.py) and the JSON bridge (bridge.py) both call these, so the logic
exists exactly once. Nothing here prints; nothing here executes or networks.
"""
import os
from datetime import datetime as _dt
from datetime import timezone as _tz

from . import state as st
from .anomaly import deferral_flag, shannon_bits, zscore
from .bandit import HourBandit
from .calibrate import DailyBudget, acceptance_rate, confidence_calibration
from .drift import diff as drift_diff
from .duration import DurationModel
from .forecast import holt
from .ghost import find_ghosts
from .graph import Graph, links
from .health import rank_notes, score as health_score
from . import journal as _journal
from .ledger import Ledger
from .linkrec import suggest_links
from .minhash import near_duplicates
from .naive_bayes import NaiveBayes
from .nlp import tokens
from .placement import suggest as placement_suggest
from .planner import cpm, knapsack
from .priority import PriorityModel, features
from .preset_bandit import NamedBandit
from .rhythm import day_of_week_pattern, hour_of_day_pattern, notable
from . import settings_bridge
from .spellfix import SpellIndex
from .srs import due, new_card, review
from .survival import completion_prob, kaplan_meier
from .textmine import keywords, summarize
from .vault import scan
from .dreamtime import eligible as dream_eligible, schedule as dream_schedule_jobs

NONE = "__none__"  # null hypothesis: untagged-note vocabulary, so a tag must beat "no tag"


def _trained_tagger(notes):
    nb = NaiveBayes()
    for note in notes.values():
        nb.train(tokens(note["text"]), note["tags"] or [NONE])
    return nb


def _has_tag_classes(nb):
    return any(c != NONE for c in nb.class_docs)


# ---- vault -----------------------------------------------------------------

def organize(vault, ledger_path, dup=0.8, min_conf=0.25):
    notes = scan(vault)
    ledger = Ledger(ledger_path)
    graph = Graph()
    for rel, note in notes.items():
        graph.add(rel.lower(), links(note["text"]))
    dups = near_duplicates({r: n["text"] for r, n in notes.items()}, threshold=dup)
    for a, b, score in dups:
        ledger.propose("merge_duplicate", f"{a} <> {b}", {"a": a, "b": b},
                       f"near-duplicate (jaccard~{score})", score)
    orphans = graph.orphans()
    for rel in orphans:
        ledger.propose("orphan", rel, {"action": "link_or_archive"},
                       "no in-links and no out-links", 0.6)
    nb = _trained_tagger(notes)
    tag_proposals = 0
    for rel, note in notes.items():
        if note["tags"] or not _has_tag_classes(nb):
            continue
        ranked = [(t, p) for t, p in nb.rank(tokens(note["text"]))
                  if t != NONE and p >= min_conf][:2]
        if ranked:
            tag_proposals += 1
            ledger.propose("tag", rel, {"add_tags": [t for t, _ in ranked]},
                           "naive-bayes tag suggestion", ranked[0][1])
    pr = sorted(graph.pagerank().items(), key=lambda x: -x[1])[:5]
    return {
        "notes": len(notes),
        "duplicate_pairs": len(dups),
        "orphans": len(orphans),
        "tag_proposals": tag_proposals,
        "communities": [c for c in graph.communities() if len(c) > 1],
        "most_connected": [k for k, _ in pr],
        "pending": len(ledger.pending()),
    }


def tag(vault, text):
    """Ranked [(tag, prob)] renormalised over tag classes, or None if untagged."""
    nb = _trained_tagger(scan(vault))
    if not _has_tag_classes(nb):
        return None
    scores = [(t, p) for t, p in nb.rank(tokens(text)) if t != NONE]
    total = sum(p for _, p in scores) or 1.0
    return [(t, p / total) for t, p in scores[:5]]


# ---- plan ------------------------------------------------------------------

def plan(tasks, minutes, state_path, ledger_path=None, propose=False, top=5):
    s = st.load(state_path)
    prio = PriorityModel.from_dict(s.get("priority", {}))
    dur = DurationModel(s.get("duration", {}).get("cats"))
    scored = []
    for t in tasks:
        x = features(t)
        est = dur.estimate(t.get("category", "general"))
        minutes_est = est["median_min"] if est["n"] >= 2 else t.get("effort_min", 30)
        score = prio.score(x)
        scored.append({"id": t["id"], "title": t.get("title", t["id"]), "score": score,
                       "x": x, "minutes": minutes_est, "value": score})
    scored.sort(key=lambda r: -r["score"])
    chosen, value, used = knapsack(
        [{"id": r["id"], "minutes": r["minutes"], "value": r["value"]} for r in scored],
        minutes)
    result = {"ranked": scored, "chosen": chosen, "value": value, "used": used,
              "critical_path": [], "project_minutes": None, "dependency_error": None,
              "proposed": 0}
    deps = {t["id"]: {"minutes": t.get("effort_min", 30), "deps": t.get("deps", [])}
            for t in tasks}
    try:
        sched = cpm(deps)
        result["critical_path"] = sorted((t for t in sched if sched[t]["critical"]),
                                         key=lambda t: sched[t]["es"])
        result["project_minutes"] = max((v["ef"] for v in sched.values()), default=0)
    except ValueError as e:
        result["dependency_error"] = str(e)
    if propose and ledger_path is not None:
        ledger = Ledger(ledger_path)
        for rank, r in enumerate(scored[:top], start=1):
            ledger.propose("priority", r["id"], {"features": r["x"], "rank": rank},
                           f"ranked {rank} of {len(scored)}", r["score"])
        result["proposed"] = min(top, len(scored))
    return result


# ---- duration --------------------------------------------------------------

def estimate_observe(category, minutes, state_path):
    s = st.load(state_path)
    dur = DurationModel(s.get("duration", {}).get("cats"))
    dur.observe(category, float(minutes))
    s["duration"] = {"cats": dur.cats}
    st.save(s, state_path)
    return dur.estimate(category)


def estimate_query(category, state_path):
    s = st.load(state_path)
    return DurationModel(s.get("duration", {}).get("cats")).estimate(category)


# ---- spaced review ---------------------------------------------------------

def review_add(card_id, state_path):
    s = st.load(state_path)
    cards = s.get("srs", {})
    cards.setdefault(card_id, new_card())
    s["srs"] = cards
    st.save(s, state_path)
    return cards[card_id]


def review_grade(card_id, rating, days, state_path):
    s = st.load(state_path)
    cards = s.get("srs", {})
    cards[card_id] = review(cards.get(card_id, new_card()), int(rating), days)
    s["srs"] = cards
    st.save(s, state_path)
    return cards[card_id]


def review_show(card_id, state_path):
    return st.load(state_path).get("srs", {}).get(card_id, {})


def review_due(days, state_path):
    cards = st.load(state_path).get("srs", {})
    return sorted(k for k, c in cards.items() if due(c, days))


# ---- reminders -------------------------------------------------------------

def remind_choose(allowed, state_path):
    bandit = HourBandit.from_dict(st.load(state_path).get("bandit", {}))
    return bandit.choose(allowed)


def remind_feedback(hour, acted, state_path):
    if not 0 <= int(hour) <= 23:
        raise ValueError("hour must be 0..23")
    s = st.load(state_path)
    bandit = HourBandit.from_dict(s.get("bandit", {}))
    bandit.reward(int(hour), bool(acted))
    s["bandit"] = bandit.to_dict()
    st.save(s, state_path)


# ---- forecast / anomaly / focus / cull ------------------------------------

def forecast(series, horizon=7):
    series = [float(x) for x in series]
    z = zscore(series[:-1], series[-1]) if len(series) >= 3 else None
    return {"forecast": holt(series, horizon=horizon), "anomaly_z": z}


def focus(labels):
    bits = shannon_bits(labels)
    return {"bits": bits, "fragmented": bits > 2.0}


def cull(history, horizon=14, threshold=0.05):
    """history: {"durations": [days], "observed": [bool], "open": [{"id", "age"}]}."""
    curve = kaplan_meier(history["durations"], history["observed"])
    flagged = []
    for t in history.get("open", []):
        p = completion_prob(curve, float(t["age"]), horizon=horizon)
        if p < threshold:
            flagged.append({"id": t["id"], "p": round(p, 3)})
    return sorted(flagged, key=lambda x: x["p"])


# ---- ledger ----------------------------------------------------------------

def ledger_list(ledger_path):
    return Ledger(ledger_path).pending()


def ledger_decide(pid, approve, ledger_path):
    return Ledger(ledger_path).decide(int(pid), bool(approve))


def ledger_learn(ledger_path, state_path):
    examples = [(i["diff"]["features"], 1 if i["status"] == "approved" else 0)
                for i in Ledger(ledger_path).labeled("priority")]
    s = st.load(state_path)
    prio = PriorityModel.from_dict(s.get("priority", {}))
    prio.fit(examples)
    s["priority"] = prio.to_dict()
    st.save(s, state_path)
    return {"examples": len(examples)}


# ---- settings (issue #120), via the ledger ---------------------------------

def settings_propose(file_path, ledger_path, preset=None, calls=None, reason=None,
                     confidence=None):
    ledger = Ledger(ledger_path)
    return settings_bridge.propose(ledger, file_path, preset=preset, calls=calls,
                                   reason=reason, confidence=confidence)


def settings_decide(pid, approve, ledger_path, state_path):
    ledger = Ledger(ledger_path)
    s = st.load(state_path)
    bandit = NamedBandit.from_dict(s.get("preset_bandit", {}))
    outcome = settings_bridge.decide(ledger, int(pid), bool(approve), bandit=bandit)
    s["preset_bandit"] = bandit.to_dict()
    st.save(s, state_path)
    return outcome


def settings_recommend(state_path, candidates=None):
    bandit = NamedBandit.from_dict(st.load(state_path).get("preset_bandit", {}))
    return settings_bridge.recommend(bandit, candidate_presets=candidates)


def settings_recommend_tools(state_path, tool_names=None):
    bandit = NamedBandit.from_dict(st.load(state_path).get("preset_bandit", {}))
    return settings_bridge.recommend_tools(bandit, tool_names)


# ---- links & text mining ----------------------------------------------------

def links_suggest(vault, ledger_path=None, propose=False, top=10, min_jaccard=0.15):
    notes = scan(vault)
    graph = Graph()
    for rel, note in notes.items():
        graph.add(rel.lower(), links(note["text"]))
    suggestions = suggest_links(graph, {r: n["text"] for r, n in notes.items()},
                                top=top, min_jaccard=min_jaccard)
    if propose and ledger_path is not None:
        ledger = Ledger(ledger_path)
        for s in suggestions:
            ledger.propose("suggest_link", f"{s['a']} <> {s['b']}",
                           {"a": s["a"], "b": s["b"], "via": s["via"]},
                           f"{s['via']} score={s['score']}", s["score"])
    return suggestions


def note_keywords(vault, note_id, top=8):
    notes = scan(vault)
    if note_id not in notes:
        raise KeyError(f"no such note: {note_id}")
    corpus = [n["text"] for rel, n in notes.items() if rel != note_id]
    return keywords(notes[note_id]["text"], corpus, top=top)


def note_summarize(vault, note_id, sentences=3):
    notes = scan(vault)
    if note_id not in notes:
        raise KeyError(f"no such note: {note_id}")
    return summarize(notes[note_id]["text"], sentences_out=sentences)


def spellcheck(vault, top=20):
    notes = scan(vault)
    return SpellIndex().build(n["text"] for n in notes.values()).suggest(top=top)


def ghosts(vault, known_task_titles, overlap_threshold=0.4):
    notes = scan(vault)
    return find_ghosts({r: n["text"] for r, n in notes.items()}, known_task_titles,
                       overlap_threshold=overlap_threshold)


# ---- decision journal --------------------------------------------------------

def journal_record(decision_id, statement, confidence, state_path):
    s = st.load(state_path)
    entries = s.get("journal", {})
    entry = _journal.record(entries, decision_id, statement, confidence)
    s["journal"] = entries
    st.save(s, state_path)
    return entry


def journal_resolve(decision_id, correct, state_path):
    s = st.load(state_path)
    entries = s.get("journal", {})
    entry = _journal.resolve(entries, decision_id, correct)
    s["journal"] = entries
    st.save(s, state_path)
    return entry


def journal_report(state_path, bins=5):
    entries = st.load(state_path).get("journal", {})
    return {"brier_score": _journal.brier_score(entries),
            "calibration": _journal.calibration_curve(entries, bins=bins)}


# ---- rhythm -------------------------------------------------------------------

def rhythm_report(weekdays, hours, threshold=1.5):
    dow = day_of_week_pattern(weekdays)
    hod = hour_of_day_pattern(hours)
    return {"day_of_week": dow, "hour_of_day": hod,
            "notable_days": notable(dow, threshold), "notable_hours": notable(hod, threshold)}


# ---- config/target placement (ISS-120-safe: proposal only, never a write) ----

def placement_propose(text, registry, ledger_path=None, propose=False, top=5):
    ranked = placement_suggest(text, registry, top=top)
    if propose and ledger_path is not None and ranked:
        ledger = Ledger(ledger_path)
        best = ranked[0]
        ledger.propose("placement", best["id"], {"query": text, "candidates": ranked},
                       f"closest match to '{text}'", best["score"])
    return ranked


# ---- calibration & proposal budget --------------------------------------------

def calibration_report(ledger_path, bins=5):
    labeled = Ledger(ledger_path).labeled()
    return {"acceptance_by_kind": acceptance_rate(labeled),
            "confidence_calibration": confidence_calibration(labeled, bins=bins)}


def budget_choose(state_path):
    s = st.load(state_path)
    budget = DailyBudget.from_dict(s.get("budget", {}))
    return budget.choose()


def budget_feedback(arm, engaged, state_path):
    s = st.load(state_path)
    budget = DailyBudget.from_dict(s.get("budget", {}))
    budget.reward(arm, bool(engaged))
    s["budget"] = budget.to_dict()
    st.save(s, state_path)


# ---- drift ---------------------------------------------------------------------

def drift_check(old_snapshot, new_snapshot, ledger_path=None, propose=False,
                similarity_threshold=0.85):
    result = drift_diff(old_snapshot, new_snapshot, similarity_threshold=similarity_threshold)
    if propose and ledger_path is not None:
        ledger = Ledger(ledger_path)
        for item_id in result["added"]:
            ledger.propose("drift_added", item_id, {"id": item_id}, "new since last snapshot", 0.9)
        for row in result["changed"]:
            ledger.propose("drift_changed", row["id"], row,
                           f"drifted (similarity={row['similarity']})", 1 - row["similarity"])
    return result


# ---- note health ----------------------------------------------------------------

def health_report(vault, dup_threshold=0.8):
    notes = scan(vault)
    graph = Graph()
    for rel, note in notes.items():
        graph.add(rel.lower(), links(note["text"]))
    orphan_ids = set(graph.orphans())
    dup_pairs = near_duplicates({r: n["text"] for r, n in notes.items()}, threshold=dup_threshold)
    dup_ids = {a for a, b, _ in dup_pairs} | {b for a, b, _ in dup_pairs}
    now = _dt.now(_tz.utc).timestamp()
    rows = []
    for rel, note in notes.items():
        try:
            age_days = max((now - os.path.getmtime(note["path"])) / 86400.0, 0.0)
        except OSError:
            age_days = 0.0
        rows.append(health_score(rel, age_days, orphan_ids, dup_ids))
    return rank_notes(rows)


# ---- idle-time scheduling --------------------------------------------------------

def dream_window(idle_minutes, on_ac_power, cpu_load_percent, jobs, budget_min):
    if not dream_eligible(idle_minutes, on_ac_power, cpu_load_percent):
        return {"eligible": False, "chosen": []}
    return {"eligible": True, "chosen": dream_schedule_jobs(jobs, budget_min)}
