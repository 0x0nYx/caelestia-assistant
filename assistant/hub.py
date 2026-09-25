"""caelestia assistant — single entry point routing to every module.

  caelestia-assist diagnose FILE | selfcheck        troubleshooting rules (Layer 1)
  caelestia-assist ask "text" [--generative]        rules, then retrieval, then optional LLM
  caelestia-assist search "query" [-k N]            offline retrieval over repo docs
  caelestia-assist issue draft|list-similar ...     issue-report drafting (never submits)
  caelestia-assist settings "request" [--apply]     natural-language shell.json editing
  caelestia-assist brain <command> ...              lean intelligence layer (proposals)
  caelestia-assist chat | route "text"              learned cortex routing (confirmation-gated)
  caelestia-assist cortex report|recall|...         learning/memory dashboard
  caelestia-assist do "anything"                    genius: universal intelligence layer
  caelestia-assist genius <command> ...             direct domain access (math/stats/...)
  caelestia-assist api < request.json               JSON bridge for the brain (QML/IPC)

Every module keeps its own safety rules; this file only routes.
"""
import sys
from typing import List, Optional

from .brain import bridge
from .brain import cli as brain_cli
from .cortex import cli as cortex_cli
from .diagnostics import cli as diagnostics_cli
from .genius import cli as genius_cli
from .issues import cli as issues_cli
from .pipeline import main as pipeline_main
from .retrieval import cli as retrieval_cli
from .settings import cli as settings_cli

USAGE = __doc__

# Some modules parse their own subcommand name (pass full argv); others take
# the remainder (the hub name is the routing token, not a module subcommand).
ROUTES = {
    "diagnose": (diagnostics_cli.main, True),
    "selfcheck": (diagnostics_cli.main, True),
    "search": (retrieval_cli.main, True),
    "ask": (pipeline_main, False),
    "issue": (issues_cli.main, False),
    "settings": (settings_cli.main, False),
    "brain": (brain_cli.main, False),
    "api": (bridge.main, False),
    # cortex: chat/route keep their own subcommand token (argparse owns it)
    "chat": (cortex_cli.main, True),
    "route": (cortex_cli.main, True),
    "cortex": (cortex_cli.main, False),
    # genius: the universal intelligence layer (its own subcommands;
    # `do` is the one-word front door)
    "do": (genius_cli.main, False),
    "genius": (genius_cli.main, False),
}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd not in ROUTES:
        print(f"caelestia-assist: unknown command {cmd!r}; try --help", file=sys.stderr)
        return 2
    fn, keep_name = ROUTES[cmd]
    return fn(argv if keep_name else rest)


def _run() -> int:
    try:
        return main()
    except BrokenPipeError:  # output piped into head/less that closed early
        return 0


if __name__ == "__main__":
    raise SystemExit(_run())
