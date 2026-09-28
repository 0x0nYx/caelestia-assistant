"""caelestia-assist eval — the measurement arena (issue #120 discipline).

Usage:
  caelestia-assist eval [suite] [--json] [--sealed]

Suites: routing | nlplan | abstention | diagnosis | calibration |
footprint | all (default: all dev suites present).

--sealed runs the sealed split. The sealed set exists to be looked at ONLY
at stage boundaries; every --sealed invocation prints a reminder to record
the look in the build state file, and the operator is trusted to do so
(the alternative — network/authors' logs — is worse).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .engine import SUITES, run_suite


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="caelestia-assist eval",
        description="the eval arena: seeded, interval-reporting measurement suites",
    )
    ap.add_argument("suite", nargs="?", default="all",
                    choices=list(SUITES) + ["all"],
                    help="which suite to run (default: all present)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--sealed", action="store_true",
                    help="run the SEALED split (record the look in the build state)")
    args = ap.parse_args(argv)

    split = "sealed" if args.sealed else "dev"
    if args.sealed:
        print("SEALED SET RUN — record this look in the build state file "
              "(limit 6 before re-authoring half the set)", file=sys.stderr)

    try:
        report = run_suite(args.suite, split=split)
    except FileNotFoundError as exc:
        print(f"eval: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        _render(report)
    return 0


def _render(report: dict) -> None:
    suites = report.get("suites", {report.get("suite", "?"): report})
    for name, rep in suites.items():
        print(f"== {name} (split {rep.get('split', '?')}, n={rep.get('n', '?')}) ==")
        for metric, val in rep.get("metrics", {}).items():
            if isinstance(val, tuple):
                print(f"  {metric}: {val[0]:.4f}  [{val[1]:.4f}, {val[2]:.4f}]")
            else:
                print(f"  {metric}: {val}")
        cw = rep.get("confident_wrong")
        if cw:
            print(f"  confident-wrong: {cw['count']}/{cw['of_routed']} routed"
                  + (f" ({cw['rate']:.1%})" if cw['rate'] is not None else ""))
        wb = rep.get("within_budget")
        if wb:
            print(f"  within budget: {wb}")
        failures = rep.get("failures")
        if failures:
            print(f"  failures ({len(failures)}):")
            for f in failures[:8]:
                print(f"    - {f.get('id')}: {f.get('text')!r} -> "
                      f"{f.get('top1') or f.get('got') or f.get('got_tool')} "
                      f"(want {f.get('accept') or f.get('expect') or f.get('expect_tool')})")
            if len(failures) > 8:
                print(f"    ... and {len(failures) - 8} more")
        if rep.get("note"):
            print(f"  note: {rep['note']}")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
