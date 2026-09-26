# Upstream PR surface plan — PROPOSED, NOT EXECUTED

**Status: a plan only. Nothing here has been sent upstream, and nothing
here should be acted on by an agent. Human decision required.**

Given the facts recorded in the captured corpus
(`assistant/retrieval/corpus/ISS-120.md`):

- issue #120 is OPEN and the assistant work is explicitly backlogged
  ("this has fallen to the backlog bc of all the more important
  features and bugfixes we need to ship first" — 0xSolanaceae,
  2026-09-22);
- the maintainer handed the issue to 0x0nYx and pointed at the shell's
  predefined agentic tools;
- no model choice, bundling decision, or in-shell API is settled;

this repo proposes the NARROWEST possible upstream-first surface — the
part that answers issue #120's actual ask without dragging the whole
intelligence layer along.

## What is proposed to go upstream FIRST (in order)

### 1. The settings/ #120 core (the "translation layer", issue #120's own words)

- `assistant/settings/parser.py` + `slots.py` — natural-language
  request -> validated tool calls over the 277-tool registry, with the
  frozen-grammar + recovery-grammar split;
- `assistant/settings/registry.py` + `tools.json` + `build_registry.py`
  — the tool registry with per-tool C++ declaration citations;
- `assistant/settings/planner.py` + `applier.py` — validated plan ->
  preview -> consent -> apply -> bounded undo (this is issue #120's
  "should only request changes through a controlled API" made real);
- `assistant/settings/consequences.py` — the what-if consequence view
  the consent card shows.

Shape of the offer: a reference implementation with its test suite,
licensed per `docs/LICENSING_OPEN_QUESTION.md`'s resolution (see that
document — nothing moves until the human licensing question is
resolved). The QML contact surface would be new but tiny: one
controller + one confirmation card.

### 2. The two-tier sidebar dispatch (the local-vs-cloud gate)

- `assistant/cortex/dispatch.py` + `delegate.py` — the decision point
  where a request stays local or hands off, and the inline-runner table;
- `cortex/conformal.py` — the conformal gate that decides the hand-off
  honestly ("below-conformal-threshold");
- the QML-side gate shape the repo already matches
  (`SettingsTools.qml` / `CommandGate.qml`: allow-list, preview,
  explicit confirm).

Shape of the offer: the dispatcher contract + tests; the shell keeps
its model and its keys, and gains a local-first tier that answers more
requests without them.

### 3. What is explicitly NOT offered upstream (this repo's standalone scope)

- `assistant/genius/` — the 18-domain intelligence layer (math,
  calculus, logic, graphs, units, ...): genuinely useful, but way
  outside issue #120's scope, and every module widens the review
  surface for no #120 gain;
- `assistant/brain/` — the personal-learning engines (bandits,
  calibration, dreamtime, drift, forecast, ...): these shape THIS
  repo's behavior from ITS user's history; they make no sense in a
  shell PR without their data;
- `assistant/brain/personal/` — the opt-in PKM engines (vault, srs,
  survival, selfcal, correlate, linkrec): documented by the personal
  README as NOT part of the #120 surface, with zero shell linkage;
- `assistant/devflow/` — the development-workflow tooling: repo-own
  scope by construction.

The second brain's lessons travel as DESIGN notes in a PR description,
not as code.

## Why this narrow order

- It matches the thread: the proposal asked for structured config
  changes through a controlled API — the settings core IS that; the
  sidebar gate is the only piece upstream needs to run the assistant
  in its own UI without shipping a model.
- It respects the backlog: small, reviewable PRs with byte-identity
  guards and pinned tests are the shape a backlogged project can
  actually take.
- It keeps the risky/licenses-unresolved material out: `docs/
  LICENSING_OPEN_QUESTION.md` gates everything, and this plan offers
  only the pieces whose safety story is self-contained (no ledger, no
  learned state, no personal data).

## What a PR would need to say

- the honest scope: what it does NOT do (no model, no network, no
  auto-apply);
- the determinism story (`docs/UPSTREAM_CASE.md`'s scoreboard);
- the license resolution from `docs/LICENSING_OPEN_QUESTION.md`;
- the test/verification contract (`selfcheck`, byte-identity, ~1,400
  green tests upstream-equivalent for the offered subset).
