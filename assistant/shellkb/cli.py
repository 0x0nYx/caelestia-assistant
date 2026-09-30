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

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)
