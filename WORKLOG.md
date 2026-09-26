# WORKLOG — caelestia-assistant engineering sessions

Append-only, one entry per work session, timestamped. A session that gets
interrupted can resume from the last entry without re-deriving context.

---

## Session 1 — 2026-09-26 (setup + Phase 1)

Task ID: setup
Agent: main agent (Super Z)

### Setup

- Cloned `0x0nYx/caelestia-assistant` (HEAD `9a28465`, branch `main`) into
  `/home/z/my-project/caelestia-assistant`. **No pre-existing working copy
  was found in the sandbox** — the fresh upstream clone IS the working
  state, so there was no upstream/working-copy divergence to reconcile.
- Cloned `ladybug-me/caelestia-kde` (HEAD `be4188f`, "Version bump to
  v2.5.0") into `/home/z/my-project/caelestia-kde` as the citation ground
  truth. Read-only reference; never modified, never pushed.
- Issue #120 state check (GitHub REST API, unauthenticated read): still
  OPEN, 14 comments, last updated 2026-09-25T17:34:30Z.
  The repo's corpus snapshot `assistant/retrieval/corpus/ISS-120.md`
  records comments only through 2026-09-23 04:38 and pins
  `repo_commit: f8760cb...` — the live issue has moved (updated 2 days
  after the snapshot's last comment). **UNVERIFIED: the newest comment
  bodies (post 2026-09-23) could not be read — API rate limit hit on
  unauthenticated calls; the PAT is deliberately NOT used for reads.
  Re-check before shipping any new ISS-120-derived citation.** The
  snapshot's core facts (thread OPEN, backlogged, not resolved) still
  match the live state.

### Baseline (before any change)

- Full suite: `python3 -m unittest discover -s . -p "test_*.py"`
  → **1049 tests, OK (skipped=5)**, ~50s.
- `python3 -m assistant.hub selfcheck` → OK.
- Baseline front-door behavior pinned: `caelestia-assist make` →
  `unknown command 'make'; try --help` (the UX failure Phase 1 fixes).

### Plan for this session

Phase 1 in order: 1.1 hub verb-tolerant routing, 1.2 generalized DELEGATE
auto-run in `cortex/cli.py`, 1.3 `agent` delegate category, 1.4 sidebar
dispatch bridge local-vs-cloud. Regression tests for each. RATIONALE.md
entry. Then Phase 2 items in the prompt's stated order (2.6 last).

### Phase 1 — SHIPPED (commit 5043d9b)

**1.1 hub verb-tolerant routing** — `assistant/hub.py`:
- Unmatched first token: unique ROUTES verb within edit distance 2 →
  "did you mean: <verb> (distance N)" on stderr, exit 1, never executed
  (ties and <5-char tokens abstain). Reuses
  `cortex/lexicon.py:levenshtein` — no second implementation.
- Otherwise the whole argv is free text →
  `cortex cli route` one-shot (read-only). Bare `help`/`-h`/`--help`
  still prints usage; "help me ..." is free text. Leading `--` honored.

**1.2 generalized DELEGATE auto-run** — new `assistant/cortex/delegate.py`
(one table of read-only runners: genius/diagnose/search/brain/issue),
wired into BOTH sites in `cortex/cli.py` (chat REPL + one-shot route),
consistent with the existing genius branch. Failure degrades to the
"try:" hint (kept as fallback, with a note). JSON mode emits
`{"verdict": "DELEGATE", "delegate": <cat>, <cat>: <payload>}`.

**1.3 agent delegate category** — `cortex/router.py`: "agent" surface
doc (archetype vocab, disjoint from brain's note vocab) + `AGENT_SEQ_RE`
sequencing floor 0.84 in PATTERN_BOOSTS. `cortex/pipeline.py`:
`agent_shaped()` (sequencing grammar + boundary crossing, checked BEFORE
the compound split shreds the sequence) → DELEGATE agent whole; per-clause
branch extended with "agent". Runner calls `agent.cli.main --simulate`
only — the execute/consent path is unreachable from conversation.

**1.4 sidebar dispatch bridge** — `cortex/dispatch.py`: runnable
DELEGATEs answer LOCALLY (inline answer = sidebar bubble +
`delegate_payload`; no gap logged). Only non-runnable delegates or
FAILED inline runs hand off (`delegate:<surface>-inline-failed`).
The QML itself needed NO change — the local-vs-cloud decision already
lives in cortex.dispatch (per its own architecture rule); AiAssistant.qml
renders outcome.action/answer as before. Verified by bridge tests per
category (`assistant/cortex/tests/test_dispatch.py`).

RATIONALE.md: new §10 with the full design rationale + safety
accounting. No settings tools / QML paths / doc anchors touched → no new
citations claimed. ALLOWED_IMPORTS.txt untouched (io/contextlib already
allowed); selfcheck green.

Live regression output (abridged; full run below):

```
test_unknown_command_is_free_text_not_an_error ... ok
test_typo_verb_gets_did_you_mean_not_a_guess ... ok
test_ambiguous_typo_does_not_guess ... ok
test_suggest_verb_tie_abstains ... ok
test_help_with_more_words_is_free_text ... ok
test_sequenced_goal_delegates_to_agent ... ok
test_more_multi_step_phrases_delegate_to_agent ... ok
test_single_step_goal_shape_delegates_to_agent ... ok
test_pure_settings_sequence_stays_compound ... ok
test_simultaneous_conjunction_is_not_agent_shaped ... ok
test_note_taking_vocabulary_stays_brain ... ok
test_inline_{genius,diagnose,search,brain,issue,agent}_* ... ok   (6)
test_inline_run_failure_keeps_the_hint_fallback ... ok
test_inline_delegate_json_shape ... ok
test_chat_repl_inline_delegate ... ok
test_delegate_answers_locally_inline ... ok
test_non_runnable_delegate_still_hands_off ... ok
test_hand_off_deduupes_by_shape_and_counts ... ok   (re-pinned, same-shape phrases)
test_bridge_dispatch_{genius,diagnose,search,brain,issue,agent}_local ... ok (6)
Ran 1076 tests in 50.4s — OK (skipped=5)     [baseline was 1049]
bash tests/test_assistant.sh → passed: 10 failed: 0
python3 -m assistant.hub selfcheck → OK
```

Three pre-existing tests pinned the OLD behavior Phase 1 explicitly
changes and were updated (not deleted) to pin the NEW behavior:
`test_unknown_command_exits_2` → free-text-not-error;
`test_delegate_hands_off_with_delegate_category` → local-inline + a
non-runnable-delegate stub guard; `test_hand_off_dedupes...` → same-shape
phrases (the old pair produced two different gap categories, one of
which now answers locally).

Definition-of-done spot check (live):
- `caelestia-assist make my bar thinner` → PROPOSED CHANGE (setBarScale)
- `caelestia-assist chatt` → "did you mean: chat (distance 1)"
- all six delegate categories answer inline via `route "<phrase>"`
- `tell me about quantum chromodynamics` → still cloud (router-abstain)

### Phase 2 progress (this session)

**2.1 SHIPPED (commit 1b51183)** — `genius/fsbrain.py` + CLI
(`genius fsbrain stale|dupes|graph|filetype [--correct TYPE]`) + 24
tests. Staleness = sysintel frecency generalized to stat() events +
Shannon entropy over category mixes (propose-only). Near-dups =
scan.simhash + Manku banding. Knowledge graph = TF-IDF
(brain.textmine, corpus=other docs) + RAKE phrases over
brain.personal.graph.Graph's PageRank/communities (reused verbatim).
Filetype = offset-anchored magic table via scan.ac + online-correctable
NaiveBayes (corrections persist as bounded reviewable docs in brain
state). **Event-watch finding (measured, live)**: select() on dirfds is
ALWAYS ready on this platform; ctypes is banned by ALLOWED_IMPORTS →
no watcher shipped (a select-loop would be a disguised poll loop — §5
violation). Audit: zero sleep-loops/pollers exist in the codebase.
Documented in RATIONALE known-gaps.

**2.2 SHIPPED (commit 7901ac4)** — graphs: astar CLI + edmonds_karp
max-flow/min-cut (Edmonds & Karp 1972) + label-propagation communities
(adapted through brain.personal.graph — not reimplemented) +
graph_algorithms meta domain. logic.schedule_resources: the general
resource-contention primitive over the existing CSP+AC-3 (settings
surface untouched). optimize: branch_and_bound (LP bound; exhaustively
cross-checked) + deterministic tabu_search (Glover 1986). data: ncd
(zlib+bz2 — bz2 added to ALLOWED_IMPORTS as a documented named
exception after the import tripwire correctly fired), bocpd (Adams &
MacKay 2007 — the changepoint-arm/prior-predictive bug was caught by
ground-truth tests and pinned), decompose_robustness (period±1 +
trimmed pass, flatness-epsilon sign agreement). 37 tests. CLI: genius
schedule / graphs astar|maxflow|communities / optimize bandb|tabu /
data --ncd --bocpd --robustness.

**2.3 SHIPPED (commit 2e21af5)** — five goal archetypes on the same
HTN consent/simulate contract: config_hygiene (lint + drift +
standard-gate reconciliation; type-mismatch stays manual — the
planner's no-structural-repair doctrine honored, pinned by test);
package_audit (agent/pkgprobe.py — FIRST quarantined subprocess module:
schema_lint per-module carve-out, exemption pinned by test, fixed arg
arrays, read-only, capability kill-switch OFF by default; static local
keyword list, NOT a CVE feed); log_triage (sysintel template mining →
issues/ drafting — the two packages now compose); notification_triage
(PURE classifier; live DBus observation documented as a gap — needs
the quarantined DBus surface + maintainer sign-off per the proposal's
own escalation); screenshot_diff (pixel-region block hashing, NO OCR,
through the ONE PNG decoder — palette_extract.png_grid refactor).
`assistant/capabilities.py`: the per-install manifest + hub
`capabilities` route. Engine latent bug fixed (results addressable by
action name — fix_plan/explain composition now actually fires).
26 tests.

Suite: 1162 green (baseline 1049); selfcheck + bash harness green at
every step. Remaining this phase: 2.4 (self-learning), 2.5 (plan
cache), 2.7 (dbus + what-if), then 2.6 last (registry adapter +
lexicon-diff + manifest registration), then Phases 3-4.
