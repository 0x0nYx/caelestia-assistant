"""caelestia assistant — single entry point routing to every module.

  caelestia-assist diagnose FILE | selfcheck        troubleshooting rules (Layer 1)
  caelestia-assist ask "text" [--generative]        rules, then retrieval, then optional LLM
  caelestia-assist search "query" [-k N]            offline retrieval over repo docs
  caelestia-assist scan FILE [--pattern P]          one-pass bounded-memory log scanning
  caelestia-assist issue draft|list-similar ...     issue-report drafting (never submits)
  caelestia-assist settings "request" [--apply]     natural-language shell.json editing
  caelestia-assist brain <command> ...              lean intelligence layer (proposals)
  caelestia-assist brief                            the daily brief (ledger+plans+forecast)
  caelestia-assist chat | route "text"              learned cortex routing (confirmation-gated)
  caelestia-assist cortex report|recall|...         learning/memory dashboard
  caelestia-assist do "anything"                    genius: universal intelligence layer
  caelestia-assist genius <command> ...             direct domain access (math/stats/...)
  caelestia-assist agent "goal" [--simulate]        agentic orchestrator (consent-gated)
  caelestia-assist api < request.json               JSON bridge for the brain (QML/IPC)

Verbless front door (phase 1 routing fix): a first token that matches no
verb above is no longer a hard error. A token within edit distance 2 of
exactly one verb gets a "did you mean" prompt (the settings layer's own
correction style — never a silent guess); anything else is treated as
free text and routed through the cortex pipeline one-shot, so

  caelestia-assist "make my bar thinner"

works end to end: an answer, a pending plan, or a simulated agent plan.

Every module keeps its own safety rules; this file only routes.
"""
import sys
from typing import List, Optional, Tuple

from .cortex.lexicon import levenshtein

from .agent import cli as agent_cli
from .brain import bridge
from .brain import cli as brain_cli
from . import capabilities as capabilities_mod
from .cortex import cli as cortex_cli
from .diagnostics import cli as diagnostics_cli
from .genius import cli as genius_cli
from .issues import cli as issues_cli
from .pipeline import main as pipeline_main
from .retrieval import cli as retrieval_cli
from .scan import cli as scan_cli
from .settings import cli as settings_cli

USAGE = __doc__

# Some modules parse their own subcommand name (pass full argv); others take
# the remainder (the hub name is the routing token, not a module subcommand).
ROUTES = {
    "diagnose": (diagnostics_cli.main, True),
    "selfcheck": (diagnostics_cli.main, True),
    "search": (retrieval_cli.main, True),
    "scan": (scan_cli.main, False),
    "ask": (pipeline_main, False),
    "issue": (issues_cli.main, False),
    "settings": (settings_cli.main, False),
    "brain": (brain_cli.main, False),
    # brief/tidy are brain subcommands surfaced at the top level too
    "brief": (lambda _argv=None: brain_cli.main(["brief"]), False),
    "tidy": (brain_cli.main, False),
    "api": (bridge.main, False),
    # cortex: chat/route keep their own subcommand token (argparse owns it)
    "chat": (cortex_cli.main, True),
    "route": (cortex_cli.main, True),
    "cortex": (cortex_cli.main, False),
    # genius: the universal intelligence layer (its own subcommands;
    # `do` is the one-word front door)
    "do": (genius_cli.main, False),
    "genius": (genius_cli.main, False),
    # agent: the consent-gated orchestrator over every layer
    "agent": (agent_cli.main, False),
    # capabilities: the per-install manifest card (read-only listing)
    "capabilities": (lambda _argv=None: (_print_card(), 0)[1], False),
}


def _print_card() -> None:
    print(capabilities_mod.render())


# Verb suggestion bounds: the same discipline the rest of the assistant
# already applies. Distance 2 is the settings CLI's forgiveness bound
# (``settings --tool setBarPositin`` -> "did you mean setBarPosition
# (distance 1)"); tokens shorter than 5 characters are never suggested
# against (the router's own min-length guard — at distance 2 short garbage
# starts matching real verbs, and a wrong suggestion is worse than none).
_SUGGEST_MAX_DISTANCE = 2
_SUGGEST_MIN_LEN = 5


def suggest_verb(cmd: str) -> Optional[Tuple[str, int]]:
    """The unique ROUTES verb within edit distance 2 of ``cmd``.

    Reuses ``cortex/lexicon.py``'s ``levenshtein`` (the single edit-distance
    implementation the router's query-side correction already uses) — this
    is a caller, not a second implementation. Returns ``(verb, distance)``
    only when exactly one verb is closest (ties are abstentions, mirroring
    the router's unique-correction rule); ``None`` otherwise.
    """
    if len(cmd) < _SUGGEST_MIN_LEN or not cmd.isalpha():
        return None
    lowered = cmd.lower()
    ranked: List[Tuple[int, str]] = []
    for verb in ROUTES:
        distance = levenshtein(lowered, verb, cap=_SUGGEST_MAX_DISTANCE)
        if distance <= _SUGGEST_MAX_DISTANCE:
            ranked.append((distance, verb))
    if not ranked:
        return None
    ranked.sort()
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None  # ambiguous: two verbs equally close — do not guess
    return ranked[0][1], ranked[0][0]


def _route_free_text(argv: List[str]) -> int:
    """The verbless front door: whole argv as one request, through the
    cortex pipeline one-shot (read-only routing; writes stay behind the
    chat confirmation gate). A leading ``--`` separator is dropped so
    `caelestia-assist -- make my bar thinner` reads naturally too."""
    words = argv[1:] if argv and argv[0] == "--" else argv
    text = " ".join(words).strip()
    if not text:
        print(USAGE)
        return 0
    # Guard argparse from a free-text phrase that happens to start with
    # a dash: everything after `--` is the positional, never an option.
    guard = ["--"] if text.startswith("-") else []
    return cortex_cli.main(["route", *guard, text])


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] in ("-h", "--help", "help") and len(argv) == 1):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd not in ROUTES:
        near = suggest_verb(cmd)
        if near is not None:
            verb, distance = near
            # The settings layer's own correction voice: the suggestion is
            # printed, never executed — the user re-runs the right verb.
            print(f"caelestia-assist: unknown command {cmd!r}", file=sys.stderr)
            print(f"did you mean: {verb} (distance {distance})", file=sys.stderr)
            return 1
        return _route_free_text(argv)
    fn, keep_name = ROUTES[cmd]
    return fn(argv if keep_name else rest)


def _run() -> int:
    try:
        return main()
    except BrokenPipeError:  # output piped into head/less that closed early
        return 0


if __name__ == "__main__":
    raise SystemExit(_run())
