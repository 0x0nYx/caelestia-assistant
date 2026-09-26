"""CLI for the settings layer (DESIGN.md §5):

    python3 -m assistant.settings "<text>" [--apply] [--file PATH] [--json]
    python3 -m assistant.settings --call NAME=VALUE [--call ...] [--apply] [--file PATH] [--json]
    python3 -m assistant.settings --list-tools [--group SLUG]
    python3 -m assistant.settings --tool NAME
    python3 -m assistant.settings --restore [--file PATH]

Guarantees:

- Dry-run by default: without --apply nothing is written — not the target,
  not a backup, not a tmp file — and the printed plan ends with the exact
  re-run command including --apply, so the confirmation step is a
  copy-paste (§5.2). This is the CLI equivalent of #120's "confirmation
  for larger changes".
- Exit codes (§5.1): 0 for every honest verdict (INTENT / AMBIGUOUS /
  NO_INTENT / SUGGESTED, including dry-run plans containing REJECTED
  entries) and for a successful apply/restore/list; 1 for operational
  failures (target file invalid JSON or non-object, unreadable file,
  --apply on a blocked plan, write failure, --restore with no backup);
  2 for usage errors (argparse's default).
- --call (direct tool addressing): NAME is a registry tool name,
  VALUE is parsed as JSON (true/false, numbers, quoted strings; a bare
  unquoted token that fails JSON parsing is treated as a plain string).
  Each --call becomes one {"tool", "action": "set", "value", "raw"} op
  and is routed through the SAME planner/render/--apply path as NL
  requests — this is how presets and model-driven callers address tools
  without the NL parser. A --call run whose plan contains any error entry
  (unknown tool, out-of-range value, bad enum, string-valued tool) exits 1
  even in dry-run: a direct invocation with a bad name or value is a
  caller error, not an honest NL verdict. --call and the positional
  request sentence are mutually exclusive (usage error, exit 2).
- Default target: $XDG_CONFIG_HOME/caelestia/shell.json falling back to
  $HOME/.config/caelestia/shell.json (the same two env vars Layer 1
  already allowlists); never any other path unless --file says so.
- No execution, no network: suggested commands are inert
  SUGGESTED_NOT_EXECUTED strings; the only writes are the ones the
  applier performs behind --apply.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import applier, parser, planner, registry
from .registry import ToolSpec, format_value, list_tools_lines, tool_by_name

PROG = "python3 -m assistant.settings"

# The string-kind pre-check message: the planner validates
# bool/enum/number values only, so string-valued tools are rejected here,
# before the planner is asked to resolve the op.
CALL_STRING_TOOLS_MESSAGE = (
    "string-valued tools are not settable through --call yet "
    "(registry-only until the planner gains string support)"
)


def default_target() -> Path:
    """§5.1: $XDG_CONFIG_HOME/caelestia/shell.json, falling back to
    $HOME/.config/caelestia/shell.json (QStandardPaths' GenericConfigLocation
    resolves exactly these two; [C7][C29])."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "caelestia" / "shell.json"


def _shell_quote(text: str) -> str:
    """Minimal double-quoting for the re-run command line (stdlib-only)."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# Rendering (§5.5). --json emits the same structure, machine-readable.
# ---------------------------------------------------------------------------


def _header(apply_mode: bool) -> List[str]:
    return [
        "caelestia assistant — settings layer (NL -> validated tool calls; dry-run by default)",
        "Nothing is written without --apply; this run writes nothing.",
    ] if not apply_mode else [
        "caelestia assistant — settings layer (NL -> validated tool calls; dry-run by default)",
        "Writes are gated: this run writes only the target file and its .assistant-backup sibling.",
    ]


def _rerun(text: str, file_arg: Optional[str], extra: str,
           call_args: Optional[List[str]] = None) -> str:
    """The exact re-run command (§5.2): confirmation as a copy-paste."""
    parts = [PROG]
    if call_args:
        for call in call_args:
            parts.append(f"--call {_shell_quote(call)}")
    if text:
        parts.append(_shell_quote(text))
    if file_arg:
        parts.append(f"--file {file_arg}")
    parts.append(extra)
    return " ".join(parts)


def _render_entry(index: int, entry: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    arrow = f"{entry['path']}: {format_value(entry['old'])} -> {format_value(entry['new'])}"
    action = entry.get("action") or ""
    raw = entry.get("raw")
    paren = f"({entry['tool']}, {action} {raw})" if raw else f"({entry['tool']}, {action})"
    if entry.get("error"):
        lines.append(f"  {index}. {arrow}  {paren} — REJECTED: {entry['error']}")
    elif entry.get("no_op"):
        lines.append(f"  {index}. {arrow}  {paren} [no change needed]")
    else:
        lines.append(f"  {index}. {arrow}  {paren}")
    if entry.get("note"):
        lines.append(f"     note: {entry['note']}")
    return lines


def render_plan(plan: Dict[str, Any], parse_notes: List[str], text: str,
                file_arg: Optional[str], apply_mode: bool,
                apply_result: Optional[Dict[str, Any]],
                call_args: Optional[List[str]] = None) -> List[str]:
    lines = ["caelestia assistant — settings layer (NL -> validated tool calls; dry-run by default)"]
    if apply_result is not None and apply_result.get("written"):
        lines.append(f"Writes are gated: this run wrote {plan['file']} and its .assistant-backup sibling.")
    elif apply_result is not None and apply_result.get("no_changes"):
        lines.append("Nothing is written without --apply; this run wrote nothing (no changes were needed).")
    elif apply_mode:
        lines.append("Writes are gated: this run writes only the target file and its .assistant-backup sibling.")
    else:
        lines.append("Nothing is written without --apply; this run writes nothing.")
    lines.append("")

    entries = plan.get("entries", [])
    notes = list(parse_notes) + list(plan.get("notes", []))
    if apply_result is not None and apply_result.get("written"):
        lines.append(f"Verdict: INTENT — {len(entries)} change(s) applied on {plan['file']}")
    else:
        lines.append(f"Verdict: INTENT — {len(entries)} change(s) planned on {plan['file']}")
    for idx, entry in enumerate(entries, start=1):
        lines.extend(_render_entry(idx, entry))
    if plan.get("apply_blocked"):
        lines.append(
            "apply_blocked: this plan contains rejected or type-mismatched entries; "
            "--apply will refuse to write anything"
        )
    if notes:
        lines.append("notes:")
        lines.extend(f"  - {note}" for note in notes)
    if apply_result is not None:
        lines.append(apply_result["message"])
        if apply_result.get("written"):
            lines.append(f"undo with: {_rerun('', file_arg, '--restore')}")
    else:
        # §5.2: the printed plan ends with the exact re-run command.
        lines.append(f"Apply with: {_rerun(text, file_arg, '--apply', call_args)}")
    return lines


def render_verdict(result: Dict[str, Any]) -> List[str]:
    """Render AMBIGUOUS / NO_INTENT / SUGGESTED verdicts (§5.5)."""
    lines = _header(False)
    lines.append("")
    verdict = result["verdict"]
    if verdict == "AMBIGUOUS":
        if result.get("candidates"):
            lines.append("Verdict: AMBIGUOUS — several settings fit; name one:")
            for idx, cand in enumerate(result["candidates"], start=1):
                lines.append(f"  {idx}. {cand['description']}")
        else:
            lines.append("Verdict: AMBIGUOUS — the request is not specific enough to act on safely.")
        if result.get("notes"):
            for note in result["notes"]:
                lines.append(f"  note: {note}")
        if result.get("question"):
            lines.append(f"Clarify: {result['question']}")
    elif verdict == "NO_INTENT":
        lines.append("Verdict: NO supported setting matched.")
        for note in result.get("notes", []):
            lines.append(f"  {note}")
        if result.get("question"):
            lines.append(f"Clarify: {result['question']}")
    elif verdict == "SUGGESTED":
        lines.append(
            "Verdict: SUGGESTED — this request is real, but it lives outside shell.json "
            "(the scheme/wallpaper system); nothing was executed and nothing was written."
        )
        for suggestion in result.get("suggestions", []):
            lines.append(f"  {suggestion}")
        for note in result.get("notes", []):
            lines.append(f"  note: {note}")
    return lines


# ---------------------------------------------------------------------------
# --list-tools / --tool (registry inspection; these never write anything).
# ---------------------------------------------------------------------------


def _list_tools_lines(group: Optional[str]) -> List[str]:
    """The --list-tools table: group-filtered when --group is given (the
    registry itself renders per-group subtotal lines when unfiltered)."""
    return list_tools_lines(group)


def _tool_card(spec: ToolSpec) -> List[str]:
    """The --tool NAME detail card: every registry fact we hold about one
    tool, including every citation line ("file:line — what it evidences").
    Fields the current registry build does not carry (group, citations on
    the 18-tool core) are rendered as explicit absences, never guessed."""
    if spec.kind == "enum":
        enum_values = "|".join(spec.enum or ()) or "(none)"
        validation = f"enum {enum_values}"
    elif spec.kind == "bool":
        validation = "on/off"
    elif spec.kind == "string":
        validation = "string"
    else:
        low = "(unbounded)" if spec.minimum is None else spec.minimum
        high = "(unbounded)" if spec.maximum is None else spec.maximum
        validation = f"range {low}-{high}"
    group = getattr(spec, "group", None)
    citations = getattr(spec, "citations", None) or ()
    lines = [
        "caelestia assistant — settings layer: tool detail",
        "",
        f"  name:        {spec.name}",
        f"  path:        {spec.path}",
        f"  group:       {group if group else '(no group metadata in this registry build)'}",
        f"  kind:        {spec.kind}",
        f"  validation:  {validation}",
        f"  default:     {format_value(spec.default)}",
        f"  global-only: {'yes' if spec.global_only else 'no'}",
        f"  step:        {spec.step if spec.step else '(not steppable)'}",
        f"  nouns:       {'; '.join(spec.nouns) if spec.nouns else '(none)'}",
        "  citations:",
    ]
    if not citations:
        lines.append("    (none recorded in this registry build)")
        return lines
    for citation in citations:
        if isinstance(citation, (tuple, list)) and len(citation) >= 2:
            lines.append(f"    {citation[0]} — {citation[1]}")
        else:
            lines.append(f"    {citation}")
    return lines


# ---------------------------------------------------------------------------
# --call NAME=VALUE (direct tool addressing): parse into planner
# ops, with two CLI-side pre-checks that produce error entries WITHOUT
# calling the planner for that op (the planner only knows bool/enum/number).
# ---------------------------------------------------------------------------


def _parse_call_value(value_text: str) -> Any:
    """VALUE is parsed as JSON (true/false, numbers, quoted strings); a
    bare unquoted token that fails JSON parsing is a plain string."""
    try:
        return json.loads(value_text)
    except ValueError:
        return value_text


def _call_error_entry(spec: Optional[ToolSpec], name: str, raw: str,
                      error: str) -> Dict[str, Any]:
    """A planner-shaped error entry synthesized by the CLI (same keys as
    planner._error_entry) for ops the planner must not be asked to resolve."""
    return {
        "tool": spec.name if spec is not None else name,
        "path": spec.path if spec is not None else "",
        "action": "set",
        "raw": raw,
        "old": None,
        "new": None,  # an errored entry is never applied
        "clamped": False,
        "no_op": False,
        "note": None,
        "error": error,
    }


def _compose_call_ops(calls: List[str]) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """Turn --call NAME=VALUE flags into planner ops.

    Returns (ops, cli_errors): ``ops`` holds the ops the planner should
    resolve (in flag order); ``cli_errors`` maps each rejected flag's
    position to a ready-made error entry. Raises ValueError for malformed
    flags (no '=' / empty name) — a usage error, exit 2.
    """
    ops: List[Dict[str, Any]] = []
    cli_errors: Dict[int, Dict[str, Any]] = {}
    for position, call in enumerate(calls):
        name, sep, value_text = call.partition("=")
        if not sep or not name:
            raise ValueError(f"--call expects NAME=VALUE (got {call!r})")
        value = _parse_call_value(value_text)
        op = {"tool": name, "action": "set", "value": value, "raw": call}
        spec = tool_by_name(name)
        if spec is None:
            # Unknown tool: the planner's existing unknown-tool error entry
            # (it renders through the same REJECTED path).
            ops.append(op)
            continue
        if getattr(spec, "kind", "") == "string":
            # The planner validates bool/enum/number values only; string
            # tools are rejected here, before the planner sees the op.
            cli_errors[position] = _call_error_entry(
                spec, name, call, CALL_STRING_TOOLS_MESSAGE)
            continue
        if isinstance(value, float) and not math.isfinite(value):
            # json.loads accepts NaN/Infinity; the planner's range checks
            # cannot reject them (all comparisons with NaN are False), so
            # they are stopped here — they can never be written as JSON.
            cli_errors[position] = _call_error_entry(
                spec, name, call,
                f"value {value_text!r} is not a finite number; "
                "NaN/Infinity are not valid JSON values",
            )
            continue
        ops.append(op)
    return ops, cli_errors


def _splice_call_errors(plan: Dict[str, Any],
                        cli_errors: Dict[int, Dict[str, Any]], total: int) -> None:
    """Merge the CLI-synthesized error entries back into the plan at their
    original --call positions, extend the plan's error list and mark it
    apply_blocked (all-or-nothing, §4.5)."""
    if not cli_errors:
        return
    merged: List[Dict[str, Any]] = []
    planner_entries = plan.get("entries", [])
    planner_index = 0
    for position in range(total):
        if position in cli_errors:
            merged.append(cli_errors[position])
        else:
            merged.append(planner_entries[planner_index])
            planner_index += 1
    plan["entries"] = merged
    errors = plan.setdefault("errors", [])
    for entry in cli_errors.values():
        errors.append(
            {"tool": entry["tool"], "path": entry["path"], "error": entry["error"]}
        )
    plan["apply_blocked"] = True


# ---------------------------------------------------------------------------
# Argument parsing and dispatch.
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    arg_parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "caelestia assistant settings layer (#120): natural-language request "
            "-> validated tool calls on the shell's shell.json. Dry-run by default; the only "
            "writes are the target file behind --apply plus its .assistant-backup sibling."
        ),
        epilog="Nothing is ever executed; suggested commands are inert strings.",
    )
    arg_parser.add_argument(
        "text", nargs="?", default=None,
        help='the request, e.g. "make the bar thinner" (required unless '
             "--list-tools/--tool/--restore/--call)",
    )
    gate = arg_parser.add_mutually_exclusive_group()
    gate.add_argument(
        "--apply", action="store_true",
        help="actually write the planned changes (default: dry-run, nothing written)",
    )
    gate.add_argument(
        "--restore", action="store_true",
        help="undo: put the single .assistant-backup slot back (one level of undo)",
    )
    arg_parser.add_argument(
        "--file", metavar="PATH", default=None,
        help=f"target shell.json override (default: {default_target()})",
    )
    arg_parser.add_argument(
        "--json", action="store_true", help="emit the machine-readable plan/verdict as JSON"
    )
    arg_parser.add_argument(
        "--list-tools", action="store_true",
        help="print the tool registry table (every tool with path, type, range) and exit",
    )
    arg_parser.add_argument(
        "--group", metavar="SLUG", default=None,
        help="feature-area filter for --list-tools (default: all groups)",
    )
    arg_parser.add_argument(
        "--tool", metavar="NAME", default=None,
        help="print a detail card for one tool (path, validation, citations) and exit",
    )
    arg_parser.add_argument(
        "--call", action="append", dest="calls", metavar="NAME=VALUE",
        help="direct tool call: NAME is a registry tool name, VALUE is JSON "
             "(true/false, number, quoted string; a bare token that fails JSON "
             "parsing is a plain string); repeatable — multiple --call flags "
             "compose one multi-op plan",
    )
    arg_parser.add_argument(
        "--explain", metavar="QUERY", default=None,
        help="read-only: explain a setting's current state (a dotted path, a "
             "tool name, or a plain-words question like 'why is my dock "
             "blurry'); never writes",
    )
    arg_parser.add_argument(
        "--history", action="store_true",
        help="read-only: list the bounded undo history (newest first) and exit",
    )
    arg_parser.add_argument(
        "--prefer", nargs=2, metavar=("PRESET_A", "PRESET_B"), default=None,
        help="opt-in pairwise comparison: dry-run previews of both presets "
             "side by side, then record which you pick (feeds the Elo/"
             "Bradley-Terry ladder; writes one comparison row to the "
             "assistant state, never to shell.json)",
    )
    arg_parser.add_argument(
        "--rank", action="store_true",
        help="read-only: print the learned pairwise preference ladder for "
             "presets (Elo + Bradley-Terry, with comparison counts)",
    )
    arg_parser.add_argument(
        "--undo", nargs="?", const=1, default=None, type=int, metavar="STEPS",
        help="undo the newest STEPS applies (default 1) from the bounded "
             "history; writes only the reverted values",
    )
    arg_parser.add_argument(
        "--undo-id", type=int, default=None, metavar="ID",
        help="revert one specific history entry (see --history) — the "
             "'restore the theme I had yesterday' operation",
    )
    arg_parser.add_argument(
        "--preset", metavar="NAME", default=None,
        help="apply a named preset (compact, minimal, gaming, battery-saver, "
             "macos-like) — a bundle of validated tool calls; multi-change, "
             "so it always shows the preview and needs --confirm/--apply",
    )
    arg_parser.add_argument(
        "--list-presets", action="store_true",
        help="print the preset table (name, description, bundled calls) and exit",
    )
    arg_parser.add_argument(
        "--confirm", action="store_true",
        help="second consent for multi-change applies: without it (and without "
             "an interactive yes), a plan touching more than one setting is "
             "previewed but NOT written",
    )
    arg_parser.add_argument(
        "--lint", action="store_true",
        help="read-only config health lint of the target shell.json (unknown "
             "keys, out-of-range or mistyped values, silent no-ops, inert "
             "customizations); never writes",
    )
    arg_parser.add_argument(
        "--wallpaper-palette", metavar="PATH", default=None,
        help="read-only: derive a WCAG-checked accent candidate from a "
             "wallpaper PNG (k-means in OKLab) and surface it through the "
             "same inert scheme-suggestion path as accent-color requests",
    )
    arg_parser.add_argument(
        "--wizard", action="store_true",
        help="first-run setup wizard: pairwise tradeoff questions -> AHP "
             "weights -> TOPSIS over the shipped presets -> a starting-preset "
             "recommendation (writes nothing; apply via --preset yourself)",
    )
    arg_parser.add_argument(
        "--answers", metavar="N,N,N,N,N,N", default=None,
        help="non-interactive wizard answers, one 1-5 intensity per "
             "question, in the order --wizard prints them",
    )
    return arg_parser


def _preview_block(plan: Dict[str, Any], label: str) -> List[str]:
    """The issue #120 preview, verbatim in shape:
    "I found several changes that match your request:" + one line per
    change + "Apply these changes?"."""
    lines = ["I found several changes that match your request"
             + (f" ({label})" if label else "") + ":"]
    for entry in plan.get("entries", []):
        if entry.get("error") or entry.get("no_op"):
            continue
        lines.append(f"- {entry.get('path')}: "
                     f"{entry.get('old', '(unset)')} -> {entry.get('new')}")
    lines.append("Apply these changes?")
    return lines


def _confirm_multi(plan: Dict[str, Any], args: Any) -> Tuple[bool, str]:
    """The multi-change confirmation gate (issue #120).

    --confirm: explicit second consent. Interactive tty: the preview plus a
    y/N prompt. Otherwise: refusal with the re-run hint. Never guesses."""
    label = getattr(args, "text", None) or ""
    if getattr(args, "confirm", False):
        return True, ""
    if sys.stdin is not None and sys.stdin.isatty():
        print("\n".join(_preview_block(plan, label)))
        try:
            answer = input("Apply these changes? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer in ("y", "yes"):
            return True, ""
        return False, "not confirmed; nothing was written"
    return False, (
        "multi-change plans need confirmation: re-run with --confirm "
        "(or answer the prompt interactively); nothing was written"
    )


def main(argv: Optional[List[str]] = None) -> int:
    arg_parser = _build_arg_parser()
    args = arg_parser.parse_args(argv)

    if args.calls is not None and args.text is not None:
        arg_parser.error(
            "--call and a request sentence are mutually exclusive: address tools "
            "directly with --call, or describe the change in plain words"
        )
    if args.group is not None and not args.list_tools:
        arg_parser.error("--group is only valid together with --list-tools")
    if args.undo is not None and args.undo_id is not None:
        arg_parser.error("--undo and --undo-id are mutually exclusive")

    if args.list_presets:
        from . import presets as presets_mod
        print("\n".join(presets_mod.describe_lines()))
        return 0

    if args.preset is not None:
        # A preset is a bundle of validated tool calls riding the ordinary
        # plan path — never a bespoke writer.
        from . import presets as presets_mod
        try:
            ops = presets_mod.preset_ops(args.preset)
        except presets_mod.PresetError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        target = Path(args.file) if args.file else default_target()
        try:
            plan = planner.plan(ops, target)
        except planner.PlannerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not args.apply:
            print("\n".join(render_plan(plan, [], f"preset: {args.preset}",
                                       args.file, False, None, None)))
            return 0
        confirmed, why = _confirm_multi(plan, args)
        if not confirmed:
            print(why, file=sys.stderr)
            return 1
        try:
            apply_result = applier.apply(
                plan, target, write=True, label=f"preset: {args.preset}")
        except applier.ApplierError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(render_plan(plan, [], f"preset: {args.preset}",
                                   args.file, True, apply_result, None)))
        return 0

    if args.rank:
        # Phase 2.4: the learned pairwise ladder — read-only, over the
        # comparison rows --prefer records. The shared ranking primitive
        # (brain/ranking.py) is the same one agent plan comparisons use.
        from ..brain import ranking as ranking_mod
        from ..brain import state as brain_state

        state = brain_state.load()
        rows = state.get("preset_comparisons") or []
        if not rows:
            print("no pairwise comparisons recorded yet; record one with "
                  "settings --prefer PRESET_A PRESET_B")
            return 0
        pairs = [(row.get("winner"), row.get("loser")) for row in rows
                 if row.get("winner") and row.get("loser")]
        report = ranking_mod.ladder_report(pairs)
        print("preset preference ladder (pairwise, learned from your "
              "explicit comparisons):")
        for row in report["ladder"]:
            conf = (f"{row['comparisons']} comparisons"
                    if row["enough_data"] else "not enough data")
            print(f"  {row['rating']:8.1f}  {row['item']:<16} ({conf})")
        tau = report["agreement_kendall_tau"]
        if tau is not None:
            print(f"elo/bradley-terry order agreement (kendall tau): {tau}")
        print("proposals only — nothing is applied; the planner/applier "
              "gates are untouched")
        return 0

    if args.prefer:
        # Phase 2.4: ONE explicit pairwise comparison (the proposal's
        # opt-in design — each pair is a deliberate choice, no batch).
        from ..brain import state as brain_state
        from . import presets as presets_mod

        name_a, name_b = args.prefer
        known = [str(p["name"]) for p in presets_mod.presets()]
        target = Path(args.file) if args.file else default_target()
        for name in (name_a, name_b):
            if name not in known:
                print(f"error: unknown preset {name!r}; known: "
                      f"{', '.join(known)}", file=sys.stderr)
                return 1
        print("\n".join(_header(False)))
        print("")
        for index, name in enumerate((name_a, name_b), 1):
            print(f"[{index}] preset {name} (dry-run, nothing written):")
            try:
                plan = planner.plan(presets_mod.preset_ops(name), target)
            except planner.PlannerError as exc:
                print(f"  planner refused: {exc}")
                continue
            print("\n".join("  " + line for line in render_plan(
                plan, [], f"prefer: {name}", args.file, False, None, None)))
        try:
            pick = input(f"which do you prefer? [1={name_a} / 2={name_b} "
                         "/ s=skip] ").strip().lower()
        except EOFError:
            pick = ""
        if pick not in ("1", "2"):
            print("no comparison recorded (skip)")
            return 0
        winner = name_a if pick == "1" else name_b
        loser = name_b if pick == "1" else name_a
        state = brain_state.load()
        rows = state.setdefault("preset_comparisons", [])
        if not isinstance(rows, list):
            rows = []
        from datetime import datetime
        rows.append({"winner": winner, "loser": loser,
                     "at": datetime.now().isoformat(timespec="seconds")})
        state["preset_comparisons"] = rows[-200:]
        brain_state.save(state)
        print(f"recorded: {winner} > {loser} (see settings --rank)")
        return 0

    if args.lint:
        # Read-only config health lint (issue #120 Phase 1.1). Never writes;
        # findings are advisory — the applier/planner remain the only gate.
        from . import lint as lint_mod
        target = Path(args.file) if args.file else default_target()
        try:
            findings = lint_mod.lint_file(target)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(_header(False)))
        print("")
        print("\n".join(lint_mod.render_findings(findings)))
        return 0

    if args.wallpaper_palette is not None:
        # Issue #120 Phase 2.4: wallpaper -> candidate accent, surfaced
        # through the EXISTING inert scheme-suggestion mechanism (same
        # constants, same renderer, same SUGGESTED_NOT_EXECUTED prefix).
        from . import parser as parser_mod
        from ..genius import palette_extract as palette_mod
        try:
            data = Path(args.wallpaper_palette).read_bytes()
            result = palette_mod.accent_from_png(data)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        suggestions = list(parser_mod.SCHEME_SUGGESTIONS) + \
            list(parser_mod.WALLPAPER_SUGGESTIONS)
        notes = [
            (f"derived from {args.wallpaper_palette}: dominant accent-like "
             f"color {result['accent']} (k-means quantization in OKLab over "
             f"{result['n_pixels']} sampled pixels; {result['selection']})"),
            (f"WCAG contrast of the derived accent: on white "
             f"{result['contrast']['on_white']['ratio']}:1, on black "
             f"{result['contrast']['on_black']['ratio']}:1 — the scheme "
             "system owns the actual change"),
            parser_mod.SCHEME_NOTE,
            "nothing was executed and nothing was written; these are inert suggestions only",
        ]
        print("\n".join(render_verdict(
            {"verdict": "SUGGESTED", "suggestions": suggestions, "notes": notes})))
        return 0

    if args.wizard:
        # Issue #120 Phase 3 "setup wizards": pure AHP+TOPSIS over the
        # shipped presets; renders a recommendation and writes nothing.
        from . import wizard as wizard_mod
        answers = None
        if args.answers:
            try:
                answers = [int(x) for x in args.answers.split(",")]
            except ValueError:
                print("error: --answers must be comma-separated integers",
                      file=sys.stderr)
                return 2
        elif args.text:
            answers = [int(x) for x in args.text.split(",")]
        if answers is not None:
            try:
                result = wizard_mod.run(answers)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print("\n".join(wizard_mod.render(result)))
            return 0
        return wizard_mod.mainish()

    if args.explain is not None:
        # Read-only explainability: never writes, never plans.
        from . import explain as explain_mod
        target = Path(args.file) if args.file else default_target()
        try:
            result = explain_mod.explain(args.explain, target)
        except explain_mod.ExplainError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(_header(False)))
        print("")
        print(result["answer"])
        if result["cites"]:
            print("grounded in: " + "; ".join(result["cites"]))
        if not result["rule"]:
            print(
                "(value readback — no causal rule fired for this key; rules "
                "needing live session state do not fire from the CLI)"
            )
        # Multi-hop provenance (Phase 1.3): best-effort and read-only —
        # missing/unreadable ledger or state files simply shorten the chain.
        try:
            from ..brain.cli import DEFAULT_LEDGER
            from ..brain import state as brain_state
            ledger_path = DEFAULT_LEDGER if Path(DEFAULT_LEDGER).exists() else None
            bandit_state = None
            state_file = Path(brain_state.DEFAULT_STATE)
            if state_file.exists():
                try:
                    bandit_state = brain_state.load().get("preset_bandit")
                except (OSError, ValueError):
                    bandit_state = None
            if ledger_path is not None or bandit_state is not None:
                prov = explain_mod.provenance(
                    args.explain, target, ledger_path=ledger_path,
                    bandit_state=bandit_state)
                if prov["chain"]:
                    print("")
                    print("\n".join(explain_mod.render_provenance(prov)))
        except ImportError:
            pass  # brain layer unavailable: value readback alone still answers
        return 0

    if args.history:
        from . import history as history_mod
        target = Path(args.file) if args.file else default_target()
        try:
            entries = history_mod.entries(target)
        except history_mod.HistoryError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(_header(False)))
        print("")
        if not entries:
            print("the undo history is empty (nothing has been applied yet)")
        else:
            print(f"undo history (newest first, {len(entries)} of "
                  f"{history_mod.MAX_ENTRIES} slots):")
            for e in entries:
                label = e.get("label") or "(unlabelled)"
                print(f"  #{e['id']}  {e['at']}  {label}  "
                      f"({len(e.get('ops', []))} change(s))")
            print("")
            print("undo with --undo (newest N) or --undo-id ID")
        return 0

    if args.undo is not None or args.undo_id is not None:
        from . import history as history_mod
        target = Path(args.file) if args.file else default_target()
        try:
            if args.undo_id is not None:
                result = history_mod.undo_by_id(target, args.undo_id)
            else:
                result = history_mod.undo(target, args.undo)
        except (history_mod.HistoryError, applier.ApplierError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(_header(False)))
        print("")
        print(result.get("message", ""))
        return 0 if result.get("restored", True) else 1

    if args.list_tools:
        # §5.1: --list-tools ignores TEXT (and writes nothing, ever).
        if args.group is not None:
            groups = tuple(registry.GROUPS)
            if args.group not in groups:
                print(
                    f"error: unknown group {args.group!r}; available groups: "
                    + ", ".join(groups),
                    file=sys.stderr,
                )
                return 1
        print("\n".join(_list_tools_lines(args.group)))
        return 0

    if args.tool is not None:
        spec = tool_by_name(args.tool)
        if spec is None:
            print(
                f"error: unknown tool {args.tool!r}; run --list-tools to see every tool",
                file=sys.stderr,
            )
            near = registry.suggest_tools(args.tool, max_distance=2)
            if near:
                shown = ", ".join(f"{name} (distance {dist})"
                                  for name, dist in near[:3])
                print(f"did you mean: {shown}", file=sys.stderr)
            return 1
        print("\n".join(_tool_card(spec)))
        return 0

    if args.restore:
        target = Path(args.file) if args.file else default_target()
        try:
            result = applier.restore(target)
        except applier.ApplierError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(_header(False)))
        print("")
        print(result["message"])
        return 0

    if args.text is None and args.calls is None:
        arg_parser.error(
            "TEXT is required unless --list-tools, --tool, --restore, --call, "
            "--explain, --history, --undo or --lint is given"
        )

    target = Path(args.file) if args.file else default_target()
    file_arg = args.file

    call_args: Optional[List[str]] = None
    cli_errors: Dict[int, Dict[str, Any]] = {}

    if args.calls is not None:
        # Direct tool addressing: compose the ops here, then ride
        # the exact same plan/render/--apply/--restore path as NL requests.
        try:
            ops, cli_errors = _compose_call_ops(args.calls)
        except ValueError as exc:
            arg_parser.error(str(exc))
        call_args = list(args.calls)
        parse_notes: List[str] = []
        text = ""
    else:
        result = parser.parse(args.text)
        verdict = result["verdict"]

        if verdict != "INTENT":
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print("\n".join(render_verdict(result)))
            return 0

        ops = result["ops"]
        parse_notes = list(result.get("notes", []))
        text = args.text

    try:
        plan = planner.plan(ops, target)
    except planner.PlannerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if cli_errors:
        _splice_call_errors(
            plan, cli_errors, total=len(args.calls) if args.calls else 0
        )

    if not args.apply:
        if args.json:
            payload = dict(plan)
            payload["notes"] = parse_notes + list(plan.get("notes", []))
            print(json.dumps(payload, indent=2))
        else:
            print("\n".join(
                render_plan(plan, parse_notes, text, file_arg, False, None, call_args)
            ))
        if args.calls is not None and plan.get("errors"):
            # A direct invocation with a bad name/value is a caller error,
            # not an honest NL verdict: exit 1 even in dry-run.
            print(
                f"error: {len(plan['errors'])} --call entry(s) rejected; "
                "nothing was written",
                file=sys.stderr,
            )
            return 1
        return 0

    # --apply: the gated write path.
    if plan.get("apply_blocked"):
        print(
            "error: apply refused — the plan contains rejected or type-mismatched entries; "
            "nothing was written",
            file=sys.stderr,
        )
        if args.json:
            payload = dict(plan)
            payload["notes"] = parse_notes + list(plan.get("notes", []))
            print(json.dumps(payload, indent=2))
        return 1

    # Issue #120's confirmation rule: a request that resolves to MORE THAN
    # ONE tool call is previewed and must be confirmed before anything is
    # written; single-setting requests apply directly (exactly as the
    # issue frames it).
    applicable_count = sum(
        1 for e in plan.get("entries", [])
        if not e.get("error") and not e.get("no_op")
    )
    if applicable_count > 1:
        confirmed, why = _confirm_multi(plan, args)
        if not confirmed:
            if args.json:
                payload = dict(plan)
                payload["notes"] = parse_notes + list(plan.get("notes", []))
                payload["confirmation"] = "required"
                print(json.dumps(payload, indent=2))
            else:
                print("\n".join(
                    render_plan(plan, parse_notes, text, file_arg, False,
                                None, call_args)))
                print("")
                print(why)
            return 1

    try:
        label = text if text else "direct --call invocation"
        apply_result = applier.apply(plan, target, write=True, label=label)
    except applier.ApplierError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = dict(plan)
        payload["notes"] = parse_notes + list(plan.get("notes", []))
        payload["applied"] = {
            "written": apply_result.get("written", False),
            "changes": apply_result.get("changes", 0),
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("\n".join(
        render_plan(plan, parse_notes, text, file_arg, True, apply_result, call_args)
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
