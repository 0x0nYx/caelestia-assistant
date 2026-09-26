"""python3 -m assistant.devflow — the developer-workflow drafting CLI.

    git diff --numstat > /tmp/numstat && python3 -m assistant.devflow commit < /tmp/numstat
    python3 -m assistant.devflow pr --base dev --head my-branch < /tmp/numstat
    python3 -m assistant.devflow todo ~/my-checkout

SCOPE: this domain serves the developer's own workflow. It has NO
relationship to issue #120 or the KDE shell and is never part of any
upstream-bound PR (see assistant/devflow/README.md).
"""
import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m assistant.devflow",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")

    commit_p = sub.add_parser("commit", help="commit-message skeleton from "
                                            "git diff --numstat text (stdin)")
    pr_p = sub.add_parser("pr", help="PR-description skeleton from the same "
                                     "stats (stdin)")
    pr_p.add_argument("--base", default="main")
    pr_p.add_argument("--head", default="dev")
    todo_p = sub.add_parser("todo", help="TODO/FIXME triage over a source tree")
    todo_p.add_argument("root", help="the tree (or single file) to triage")

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0

    if args.cmd == "commit":
        from .diffstat import commit_message
        print(commit_message(sys.stdin.read()))
        return 0
    if args.cmd == "pr":
        from .diffstat import pr_skeleton
        print(pr_skeleton(sys.stdin.read(), base=args.base, head=args.head))
        return 0
    if args.cmd == "todo":
        from .todo import render, triage_tree
        print(render(triage_tree(args.root)))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
