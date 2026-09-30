"""shellkb.cli — the shellkb command line: `caelestia-assist shellkb ...`.

One argparse over the shell employee's verbs. Every verb is read-only;
every command line it prints is labeled SUGGESTED_NOT_EXECUTED. Verbs
are added one feature-commit at a time (grammar first, B6).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import cligrammar
from . import cmdparse
from . import howto


def _grammar_cmd(args) -> int:
    if args.json:
        data = cligrammar.load_grammar()
        print(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))
        return 0
    for line in cligrammar.render_lines():
        print(line)
    print()
    for line in cligrammar.example_lines():
        print(line)
    return 0


def _explain_cmd(args) -> int:
    line = " ".join(args.command)
    data = cmdparse.explain_line(line)
    if args.json:
        print(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))
        return 0
    for out in cmdparse.render_explanation(data):
        print(out)
    return 0


def _howto_cmd(args) -> int:
    data = howto.answer(" ".join(args.question))
    if args.json:
        print(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))
        return 0
    for out in howto.render_lines(data):
        print(out)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="caelestia-assist shellkb", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="verb")

    g = sub.add_parser(
        "grammar", help="the shell CLIs' typed option grammar, induced "
                        "from upstream file text (nothing executed)")
    g.add_argument("--json", action="store_true",
                   help="the committed artifact verbatim")
    g.set_defaults(func=_grammar_cmd)

    e = sub.add_parser(
        "explain", help="explain a command line token by token; mark "
                        "destructive patterns; preview globs read-only. "
                        "Never executes anything.")
    e.add_argument("command", nargs="+",
                   help="the command line to explain (quote it as one "
                        "argument, or put -- before it)")
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=_explain_cmd)

    h = sub.add_parser(
        "howto", help="offline how-to answers from a self-authored CC0 "
                       "cheat sheet (BM25 + time expressions); commands "
                       "are SUGGESTED_NOT_EXECUTED")
    h.add_argument("question", nargs="+")
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=_howto_cmd)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)
