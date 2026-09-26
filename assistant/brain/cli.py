"""brain CLI: formats shell-native service results as text. Every change is a
proposal.

Scope note (issue #120 split): the personal-knowledge-management commands
(organize, tag, plan, estimate, review, remind, cull, links, keywords,
summarize, spellcheck, ghosts, journal, health, ledger learn) moved to
assistant/brain/personal/ with their own entry point
(`python3 -m assistant.brain.personal --help`). This CLI keeps only
operations with direct shell linkage:

  python3 -m assistant.brain forecast 3,4,5,6 [--horizon 7]
  python3 -m assistant.brain focus cat1,cat2,cat1,...
  python3 -m assistant.brain rhythm [--weekdays 0,1,1,2] [--hours 9,9,14]
  python3 -m assistant.brain calibration
  python3 -m assistant.brain ledger list | approve ID | reject ID
  python3 -m assistant.brain settings propose FILE [--preset NAME] [--call TOOL=VALUE ...] [--reason TEXT]
  python3 -m assistant.brain settings decide ID approve|reject
  python3 -m assistant.brain settings recommend [--top N] [--tools]
  python3 -m assistant.brain brief
  python3 -m assistant.brain tidy survey ROOT | rollback
  python3 -m assistant.brain prefs
"""
import argparse
import json
import pathlib
import sys

from . import service
from . import state as st

DEFAULT_LEDGER = pathlib.Path.home() / ".local/state/caelestia-brain/ledger.json"


def cmd_forecast(args, out):
    r = service.forecast([x for x in args.series.split(",")], horizon=args.horizon)
    out.write(", ".join(f"{v:.2f}" for v in r["forecast"]) + "\n")
    if r["anomaly_z"] is not None:
        out.write(f"latest value z-score vs history: {r['anomaly_z']:.2f}"
                  f"{'  (anomaly)' if abs(r['anomaly_z']) >= 2 else ''}\n")
    return 0


def cmd_focus(args, out):
    r = service.focus(args.labels.split(","))
    out.write(f"switch entropy: {r['bits']:.2f} bits"
              f"{'  (fragmented: consider a single-task block)' if r['fragmented'] else ''}\n")
    return 0


def cmd_rhythm(args, out):
    if args.settings_file or args.scheme_switches:
        # Phase 2.6: rhythm over shell events (settings applies from the
        # undo history + ledger decisions + any caller-supplied scheme
        # switch timestamps).
        r = service.settings_rhythm(args.settings_file,
                                    scheme_switches=(args.scheme_switches.split(",")
                                                     if args.scheme_switches else None),
                                    ledger_path=args.ledger)
        out.write(f"events: {r['events']}\n")
        for row in r["notable_days"]:
            out.write(f"day {row['day']}: z={row['z']} (n={row['count']})\n")
        for row in r["notable_hours"]:
            out.write(f"hour {row['hour']}: z={row['z']} (n={row['count']})\n")
        return 0
    weekdays = [int(x) for x in args.weekdays.split(",")] if args.weekdays else []
    hours = [int(x) for x in args.hours.split(",")] if args.hours else []
    r = service.rhythm_report(weekdays, hours)
    for row in r["notable_days"]:
        out.write(f"day {row['day']}: z={row['z']} (n={row['count']})\n")
    for row in r["notable_hours"]:
        out.write(f"hour {row['hour']}: z={row['z']} (n={row['count']})\n")
    return 0


def cmd_workspace(args, out):
    records = json.loads(pathlib.Path(args.sessions).read_text(encoding="utf-8"))
    r = service.workspace_profiles(records, args.ledger, propose=args.propose,
                                   k=args.k, min_support=args.min_support,
                                   purity=args.purity)
    if args.propose:
        for pid in r["proposals"]:
            out.write(f"proposal #{pid} pending (approve: brain ledger approve {pid})\n")
        if not r["proposals"]:
            out.write("no consistent co-occurrence found — nothing proposed\n")
    else:
        out.write(f"sessions: {r['n_sessions']}  clusters: {r['k']}  "
                  f"rejected: {r['rejected_clusters']}\n")
        for pr in r["profiles"]:
            out.write(f"  {pr['name']}: app={pr['app']} monitor={pr['monitor']} "
                      f"ws={pr['workspace']} support={pr['support']} "
                      f"purity={pr['purity']} mean-hour={pr['hours_mean']}\n")
        if not r["profiles"]:
            out.write("no consistent co-occurrence found\n")
        out.write("(dry-run: nothing proposed; add --propose to write "
                  "ledger proposals)\n")
    return 0


def cmd_topology(args, out):
    from ..settings.cli import default_target
    r = service.topology_observe(args.file or default_target(), args.state,
                                 args.ledger, propose=args.propose)
    fp = r["fingerprint"]
    out.write(f"monitors: {', '.join(fp['monitors']) or '(none)'}  hash: {fp['hash']}\n")
    out.write(f"changed since last observe: {r['changed']}  "
              f"remembered deltas for this set: {r['remembered']}\n")
    out.write(f"current override deltas: {len(r['deltas'])}\n")
    if r["proposal_id"] is not None:
        out.write(f"proposal #{r['proposal_id']} pending (approve: brain ledger approve {r['proposal_id']})\n")
    return 0


def cmd_calibration(args, out):
    r = service.calibration_report(args.ledger)
    for kind, s in r["acceptance_by_kind"].items():
        out.write(f"{kind}: mean={s['mean']} n={s['n']}\n")
    for row in r["confidence_calibration"]:
        out.write(f"  bucket {row['bucket']}: n={row['n']} "
                  f"avg_conf={row['avg_confidence']} approval_rate={row['approval_rate']}\n")
    return 0


def cmd_ledger(args, out):
    if args.action == "list":
        pending = service.ledger_list(args.ledger)
        for i in pending:
            out.write(f"#{i['id']} [{i['kind']}] {i['target']} conf={i['confidence']} :: {i['reason']}\n")
        if not pending:
            out.write("no pending proposals\n")
    elif args.action in ("approve", "reject"):
        service.ledger_decide(args.id, args.action == "approve", args.ledger)
        out.write(f"{args.action}d #{args.id}\n")
    return 0


def _parse_call_value(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def _calls_to_ops(calls):
    ops = []
    for call in calls or []:
        name, sep, value_text = call.partition("=")
        if not sep or not name:
            raise ValueError(f"--call expects NAME=VALUE (got {call!r})")
        ops.append({"tool": name, "action": "set", "value": _parse_call_value(value_text),
                    "raw": call})
    return ops


def cmd_settings(args, out):
    if args.action == "propose":
        file_path = args.arg1
        if not file_path:
            out.write("settings propose needs FILE\n")
            return 2
        r = service.settings_propose(file_path, args.ledger, preset=args.preset,
                                     calls=_calls_to_ops(args.calls), reason=args.reason)
        if r["proposal_id"] is None:
            out.write("nothing to propose"
                      + (" (blocked: see errors)" if r["blocked"] else " (no applicable change)")
                      + "\n")
            for err in r["errors"]:
                out.write(f"  error: {err}\n")
        else:
            out.write(f"proposal #{r['proposal_id']} pending "
                      f"(brain settings decide {r['proposal_id']} approve|reject):\n")
            for line in r["preview"]:
                out.write(f"  - {line}\n")
    elif args.action == "decide":
        pid = int(args.arg1)
        approve = args.arg2 == "approve"
        r = service.settings_decide(pid, approve, args.ledger, args.state,
                                    battery_reward=args.battery_reward)
        if r["applied"]:
            out.write(f"#{pid} approved and written\n")
        elif approve:
            out.write(f"#{pid} approved but nothing was written: "
                      f"{r.get('apply_result', {}).get('message', '')}\n")
        else:
            out.write(f"#{pid} rejected; nothing written\n")
    else:  # recommend
        if args.tools:
            recs = service.settings_recommend_tools(args.state)
            if not recs:
                out.write("no tool-level history yet\n")
            for rec in recs[:args.top]:
                out.write(f"{rec['tool']:<20} conf={rec['confidence']}\n")
        else:
            for rec in service.settings_recommend(args.state)[:args.top]:
                out.write(f"{rec['name']:<14} conf={rec['confidence']:<5} {rec['label']}\n")
    return 0


def cmd_brief(args, out):
    """Daily brief: compose what the ledger + forecasts already know."""
    from . import brief as brief_mod
    from .ledger import Ledger
    ledger = Ledger(args.ledger)
    drift = None
    if getattr(args, "config_drift", False):
        drift = _config_drift_payload(args)
    brief = brief_mod.compose(pending=ledger.pending(), config_drift=drift)
    out.write(brief_mod.render(brief) + "\n")
    return 0


def _config_drift_payload(args):
    """B2 opt-in: read the live shell.json (read-only, the planner's own
    reader) and score it against the preference posterior learned from
    the ledger. Returns the drift dict, or a thin 'why not' marker."""
    from pathlib import Path

    from . import prefs as prefs_mod
    from .ledger import Ledger
    from ..settings import cli as settings_cli
    from ..settings import planner
    target = getattr(args, "target", None) or settings_cli.default_target()
    try:
        current, _notes = planner._read_current(Path(target))
    except Exception as exc:  # PlannerError: unreadable/invalid JSON
        return {"evaluated": 0, "flags": [], "thin": [], "score": 0,
                "error": f"target unreadable ({exc}); drift not computed"}
    model = prefs_mod.PreferenceModel()
    model.from_ledger(Ledger(args.ledger).items)
    return prefs_mod.config_drift(model, current)


def cmd_tidy(args, out):
    """Filesystem organizer: survey (read-only) / rollback — apply goes via the agent."""
    from . import tidy as tidy_mod
    if args.action == "survey":
        plan = tidy_mod.survey(args.root)
        if args.json:
            out.write(json.dumps(plan, indent=2) + "\n")
        else:
            out.write(tidy_mod.render_plan(plan) + "\n")
        return 0
    if args.action == "rollback":
        res = tidy_mod.rollback(args.journal)
        out.write(f"undone {len(res['undone'])} move(s); "
                  f"missing {len(res['missing'])}\n")
        return 0
    out.write("tidy: use `survey ROOT`, `rollback` — moves are applied via the "
              "agent (`caelestia-assist agent 'clean my downloads'`), never "
              "blindly\n")
    return 2


def cmd_prefs(args, out):
    """Preference model: what the Beta posteriors currently believe."""
    from . import prefs as prefs_mod
    from .ledger import Ledger
    model = prefs_mod.PreferenceModel()
    ledger = Ledger(args.ledger)
    n = model.from_ledger(ledger.items)
    if n == 0:
        out.write("no decided proposals yet — approve/reject some and I learn "
                  "your patterns\n")
        return 0
    out.write(f"learned from {n} decision(s):\n")
    keys = sorted(model.table.keys())
    for key in keys[:12]:
        group, direction, bucket = key.split("|")
        line = model.explain(group, direction, hour=None)
        b = model.bias(group, direction, int(bucket) if int(bucket) >= 0 else None)
        out.write(f"  {group:<16} {direction:<9} bucket {bucket}: "
                  f"p={b['p_accept']} n={b['n']} ({b['verdict']})\n")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="brain", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", default=str(st.DEFAULT_STATE))
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("forecast")
    f.add_argument("series")
    f.add_argument("--horizon", type=int, default=7)
    f.set_defaults(fn=cmd_forecast)

    fo = sub.add_parser("focus")
    fo.add_argument("labels")
    fo.set_defaults(fn=cmd_focus)

    rh = sub.add_parser("rhythm")
    rh.add_argument("--weekdays", default="")
    rh.add_argument("--hours", default="")
    rh.add_argument("--settings-file", default=None,
                    help="derive events from this file's settings-apply "
                         "history and ledger decisions instead of lists")
    rh.add_argument("--scheme-switches", default="",
                    help="comma-separated ISO scheme-switch timestamps "
                         "(the scheme system persists no switch history)")
    rh.set_defaults(fn=cmd_rhythm)

    ws = sub.add_parser("workspace", help="session clustering -> workspace "
                                          "profile proposals (issue #120)")
    ws.add_argument("sessions")
    ws.add_argument("--propose", action="store_true")
    ws.add_argument("--k", type=int, default=None)
    ws.add_argument("--min-support", type=int, default=3)
    ws.add_argument("--purity", type=float, default=0.6)
    ws.set_defaults(fn=cmd_workspace)

    tp = sub.add_parser("topology", help="per-monitor-topology config memory "
                                         "(issue #120)")
    tp.add_argument("--file", default=None,
                    help="target shell.json (default: the settings layer's "
                         "default target)")
    tp.add_argument("--propose", action="store_true")
    tp.set_defaults(fn=cmd_topology)

    ca = sub.add_parser("calibration")
    ca.set_defaults(fn=cmd_calibration)

    lg = sub.add_parser("ledger")
    lg.add_argument("action", choices=["list", "approve", "reject"])
    lg.add_argument("id", nargs="?", type=int, default=0)
    lg.set_defaults(fn=cmd_ledger)

    se = sub.add_parser("settings")
    se.add_argument("action", choices=["propose", "decide", "recommend"])
    # propose: arg1=FILE. decide: arg1=ID, arg2=approve|reject. recommend: unused.
    se.add_argument("arg1", nargs="?", default="")
    se.add_argument("arg2", nargs="?", default="reject")
    se.add_argument("--preset", default=None)
    se.add_argument("--call", action="append", dest="calls", default=None)
    se.add_argument("--reason", default=None)
    se.add_argument("--top", type=int, default=10)
    se.add_argument("--tools", action="store_true",
                    help="recommend: rank individual tools instead of presets")
    se.add_argument("--battery-reward", type=float, default=None, metavar="R",
                    help="decide: optional secondary bandit signal in [0, 1] "
                         "(0.5 neutral) from battery drain-rate deltas around "
                         "the preset's active window; never replaces the "
                         "approve/reject signal")
    se.set_defaults(fn=cmd_settings)

    # ---- shell-native second-brain surfaces (brief / tidy / prefs) ----
    br = sub.add_parser("brief", help="one deterministic page connecting "
                                       "ledger, plans, forecasts")
    br.add_argument("--config-drift", action="store_true",
                    help="opt-in (B2): score the live shell.json against "
                         "the preference posterior learned from the ledger")
    br.add_argument("--target", default=None,
                    help="shell.json to score for --config-drift "
                         "(default: the watched global config)")
    br.set_defaults(fn=cmd_brief)

    td = sub.add_parser("tidy", help="filesystem survey (read-only) + rollback")
    td.add_argument("action", choices=["survey", "rollback"])
    td.add_argument("root", nargs="?", default="~/Downloads")
    td.add_argument("--journal", default=None)
    td.add_argument("--json", action="store_true")
    td.set_defaults(fn=cmd_tidy)

    pf = sub.add_parser("prefs", help="what the preference model believes "
                                      "about your approve/reject patterns")
    pf.set_defaults(fn=cmd_prefs)
    return p


def main(argv=None, out=None):
    args = build_parser().parse_args(argv)
    return args.fn(args, out or sys.stdout)
