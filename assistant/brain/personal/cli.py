"""personal CLI: the opt-in personal-knowledge-management command surface.

NOT part of the caelestia-kde issue #120 feature surface — the shell-side
brain CLI (python3 -m assistant.brain) exposes none of these commands. This
is the only entry point for the personal tools:

  python3 -m assistant.brain.personal organize VAULT [--ledger F] [--state F]
  python3 -m assistant.brain.personal tag VAULT "text to tag"
  python3 -m assistant.brain.personal plan TASKS.json --minutes 240 [--propose]
  python3 -m assistant.brain.personal estimate observe CAT MINUTES | query CAT
  python3 -m assistant.brain.personal review add|grade|due|show ...
  python3 -m assistant.brain.personal remind choose|feedback ...
  python3 -m assistant.brain.personal cull HISTORY.json [--horizon 14]
  python3 -m assistant.brain.personal links VAULT [--propose]
  python3 -m assistant.brain.personal keywords VAULT NOTE [--top N]
  python3 -m assistant.brain.personal summarize VAULT NOTE [--sentences N]
  python3 -m assistant.brain.personal spellcheck VAULT [--top N]
  python3 -m assistant.brain.personal ghosts VAULT [--known "t1,t2"]
  python3 -m assistant.brain.personal journal record|resolve|report ...
  python3 -m assistant.brain.personal health VAULT [--dup F] [--top N]
  python3 -m assistant.brain.personal ledger learn

Shared global flags --state / --ledger keep the same defaults and the same
formats as the shell-side brain CLI, so one ledger file can hold both kinds
of proposals without either surface reading the other's kinds.
"""
import argparse
import json
import pathlib
import sys

from . import service
from .. import state as st
from ..cli import DEFAULT_LEDGER


def cmd_organize(args, out):
    r = service.organize(args.vault, args.ledger, dup=args.dup, min_conf=args.min_conf)
    out.write(f"notes: {r['notes']}  duplicate pairs: {r['duplicate_pairs']}  "
              f"orphans: {r['orphans']}  tag proposals: {r['tag_proposals']}\n")
    out.write(f"communities (size>1): {len(r['communities'])}\n")
    for c in r["communities"][:10]:
        out.write(f"  [{len(c)}] {', '.join(c[:6])}{' ...' if len(c) > 6 else ''}\n")
    out.write("most-connected notes (PageRank): " + ", ".join(r["most_connected"]) + "\n")
    out.write(f"pending proposals: {r['pending']}  (see: brain ledger list)\n")
    return 0


def cmd_tag(args, out):
    ranked = service.tag(args.vault, args.text)
    if ranked is None:
        out.write("no tagged notes to learn from\n")
        return 1
    for tag_name, p in ranked:
        out.write(f"{tag_name}\t{p:.3f}\n")
    return 0


def cmd_plan(args, out):
    tasks = json.loads(pathlib.Path(args.tasks).read_text(encoding="utf-8"))
    r = service.plan(tasks, args.minutes, args.state, args.ledger,
                     propose=args.propose, top=args.top)
    out.write("ranked:\n")
    for row in r["ranked"]:
        mark = "*" if row["id"] in r["chosen"] else " "
        out.write(f" {mark} {row['score']:.3f}  ~{row['minutes']:.0f}min  {row['title']}\n")
    out.write(f"plan ({r['used']}/{args.minutes} min, value {r['value']:.2f}): "
              f"{', '.join(r['chosen'])}\n")
    if r["dependency_error"]:
        out.write(f"dependency error: {r['dependency_error']}\n")
    else:
        out.write(f"critical path: {' -> '.join(r['critical_path'])}\n")
        out.write(f"project length: {r['project_minutes']} min\n")
    if args.propose:
        out.write(f"proposed {r['proposed']} priority decisions\n")
    return 0


def cmd_estimate(args, out):
    if args.action == "observe":
        est = service.estimate_observe(args.category, args.minutes, args.state)
    else:
        est = service.estimate_query(args.category, args.state)
    out.write(json.dumps(est) + "\n")
    return 0


def cmd_review(args, out):
    if args.action == "add":
        service.review_add(args.id, args.state)
    elif args.action == "grade":
        service.review_grade(args.id, args.rating, args.days, args.state)
    elif args.action == "show":
        out.write(json.dumps(service.review_show(args.id, args.state), indent=2) + "\n")
    elif args.action == "due":
        ids = service.review_due(args.days, args.state)
        out.write("due: " + (", ".join(ids) or "none") + "\n")
    return 0


def cmd_remind(args, out):
    if args.action == "choose":
        out.write(f"{service.remind_choose(_allowed(args.allowed), args.state)}\n")
    else:
        service.remind_feedback(args.hour, args.acted == "1", args.state)
        out.write("recorded\n")
    return 0


def _allowed(spec):
    if not spec:
        return None
    a, b = spec.split("-")
    return list(range(int(a), int(b) + 1))


def cmd_cull(args, out):
    hist = json.loads(pathlib.Path(args.history).read_text(encoding="utf-8"))
    flagged = service.cull(hist, horizon=args.horizon, threshold=args.threshold)
    if not flagged:
        out.write("no cull candidates\n")
    for row in flagged:
        out.write(f"cull? {row['id']}  P(complete in {args.horizon}d)={row['p']}\n")
    return 0


def cmd_links(args, out):
    suggestions = service.links_suggest(args.vault, args.ledger, propose=args.propose,
                                        top=args.top, min_jaccard=args.min_jaccard)
    if not suggestions:
        out.write("no link suggestions\n")
    for s in suggestions:
        out.write(f"{s['a']} <-> {s['b']}  score={s['score']} ({s['via']})\n")
    return 0


def cmd_keywords(args, out):
    for w in service.note_keywords(args.vault, args.note, top=args.top):
        out.write(w + "\n")
    return 0


def cmd_summarize(args, out):
    for line in service.note_summarize(args.vault, args.note, sentences=args.sentences):
        out.write(line + "\n")
    return 0


def cmd_spellcheck(args, out):
    rows = service.spellcheck(args.vault, top=args.top)
    if not rows:
        out.write("no likely typos found\n")
    for r in rows:
        out.write(f"{r['typo']} ({r['count']}x) -> {r['likely']}? ({r['likely_count']}x)\n")
    return 0


def cmd_ghosts(args, out):
    known = args.known.split(",") if args.known else []
    rows = service.ghosts(args.vault, known, overlap_threshold=args.overlap)
    if not rows:
        out.write("no ghost tasks found\n")
    for r in rows:
        out.write(f"{r['note']}: {r['line']}\n")
    return 0


def cmd_journal(args, out):
    if args.action == "record":
        service.journal_record(args.id, args.statement, args.confidence, args.state)
        out.write("recorded\n")
    elif args.action == "resolve":
        service.journal_resolve(args.id, args.correct == "1", args.state)
        out.write("resolved\n")
    else:
        r = service.journal_report(args.state)
        out.write(f"brier score: {r['brier_score']}\n")
        for row in r["calibration"]:
            out.write(f"  bucket {row['bucket']}: n={row['n']} "
                      f"avg_conf={row['avg_confidence']} hit_rate={row['hit_rate']}\n")
    return 0


def cmd_health(args, out):
    rows = service.health_report(args.vault, dup_threshold=args.dup)
    for r in rows[:args.top]:
        flags = ",".join(k for k in ("stale", "orphan", "duplicate") if r[k])
        out.write(f"{r['score']:5.1f}  {r['id']}  [{flags}]\n")
    return 0


def cmd_ledger(args, out):
    if args.action == "learn":
        from ..cli import DEFAULT_LEDGER as _dl  # same ledger file as the shell side
        r = service.ledger_learn(args.ledger or str(_dl), args.state)
        out.write(f"learned from {r['examples']} labeled priority decisions\n")
        return 0
    out.write("personal ledger: only 'learn' lives here; list/approve/reject "
              "stay on the shell-side brain CLI\n")
    return 2


def build_parser():
    p = argparse.ArgumentParser(prog="assistant.brain.personal",
                                description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", default=str(st.DEFAULT_STATE))
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    sub = p.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("organize")
    o.add_argument("vault")
    o.add_argument("--dup", type=float, default=0.8)
    o.add_argument("--min-conf", type=float, default=0.25)
    o.set_defaults(fn=cmd_organize)

    t = sub.add_parser("tag")
    t.add_argument("vault")
    t.add_argument("text")
    t.set_defaults(fn=cmd_tag)

    pl = sub.add_parser("plan")
    pl.add_argument("tasks")
    pl.add_argument("--minutes", type=int, default=240)
    pl.add_argument("--propose", action="store_true")
    pl.add_argument("--top", type=int, default=5)
    pl.set_defaults(fn=cmd_plan)

    e = sub.add_parser("estimate")
    e.add_argument("action", choices=["observe", "query"])
    e.add_argument("category")
    e.add_argument("minutes", nargs="?", default=0)
    e.set_defaults(fn=cmd_estimate)

    r = sub.add_parser("review")
    r.add_argument("action", choices=["add", "grade", "due", "show"])
    r.add_argument("id", nargs="?", default="")
    r.add_argument("rating", nargs="?", default="3")
    r.add_argument("--days", type=float, default=0.0)
    r.set_defaults(fn=cmd_review)

    rm = sub.add_parser("remind")
    rm.add_argument("action", choices=["choose", "feedback"])
    rm.add_argument("hour", nargs="?", default="0")
    rm.add_argument("acted", nargs="?", default="0")
    rm.add_argument("--allowed", default="8-22")
    rm.set_defaults(fn=cmd_remind)

    c = sub.add_parser("cull")
    c.add_argument("history")
    c.add_argument("--horizon", type=int, default=14)
    c.add_argument("--threshold", type=float, default=0.05)
    c.set_defaults(fn=cmd_cull)

    lk = sub.add_parser("links")
    lk.add_argument("vault")
    lk.add_argument("--propose", action="store_true")
    lk.add_argument("--top", type=int, default=10)
    lk.add_argument("--min-jaccard", type=float, default=0.15)
    lk.set_defaults(fn=cmd_links)

    kw = sub.add_parser("keywords")
    kw.add_argument("vault")
    kw.add_argument("note")
    kw.add_argument("--top", type=int, default=8)
    kw.set_defaults(fn=cmd_keywords)

    sm = sub.add_parser("summarize")
    sm.add_argument("vault")
    sm.add_argument("note")
    sm.add_argument("--sentences", type=int, default=3)
    sm.set_defaults(fn=cmd_summarize)

    sp = sub.add_parser("spellcheck")
    sp.add_argument("vault")
    sp.add_argument("--top", type=int, default=20)
    sp.set_defaults(fn=cmd_spellcheck)

    gh = sub.add_parser("ghosts")
    gh.add_argument("vault")
    gh.add_argument("--known", default="")
    gh.add_argument("--overlap", type=float, default=0.4)
    gh.set_defaults(fn=cmd_ghosts)

    jr = sub.add_parser("journal")
    jr.add_argument("action", choices=["record", "resolve", "report"])
    jr.add_argument("id", nargs="?", default="")
    jr.add_argument("statement", nargs="?", default="")
    jr.add_argument("confidence", nargs="?", type=float, default=0.5)
    jr.add_argument("correct", nargs="?", default="1")
    jr.set_defaults(fn=cmd_journal)

    he = sub.add_parser("health")
    he.add_argument("vault")
    he.add_argument("--dup", type=float, default=0.8)
    he.add_argument("--top", type=int, default=15)
    he.set_defaults(fn=cmd_health)

    lg = sub.add_parser("ledger")
    lg.add_argument("action", choices=["learn"])
    lg.add_argument("id", nargs="?", type=int, default=0)
    lg.set_defaults(fn=cmd_ledger)
    return p


def main(argv=None, out=None):
    args = build_parser().parse_args(argv)
    return args.fn(args, out or sys.stdout)
