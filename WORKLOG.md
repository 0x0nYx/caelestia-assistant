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

### 2.4 + citation re-verification (commits e11020b, 3535b8a)

**2.4 SHIPPED (e11020b)** — LinUCBBandit (Li et al. 2010, disjoint
model, exact UCB bound); brain/features.py shared signed feature
hashing (Weinberger et al. 2009); Ebbinghaus half-life as per-user
brain-state setting (cortex halflife, bounds 0.5-365); brain/ranking.py
shared Elo + Bradley-Terry primitive generalized to any named items
(synthetic 300-pair ground-truth recovery per the proposal's own
verification plan); settings --prefer / --rank consumers; calibration
surfaced ("routes scored like this were right ~N% of the time (k
decisions)", >=5-observation gate). 27 tests -> 1189 green.

**Registry re-verification SHIPPED (3535b8a)** — sandbox layout fix:
ground-truth caelestia-kde clone exposed through locally-excluded
symlinks (shell/plugin, shell/components, shell/modules/{bar,drawers,
nexus}, shell/services/Colours.qml; git-ignored via .git/info/exclude,
nothing committed). With the citation guards live: all 277 tools'
C++ declarations verified against upstream HEAD (zero drift); the
byte-identity regeneration test caught real drift — committed
tools.json carried 353 dev-process reason strings vs the generator's
clean output; regenerated and re-committed (generator stays the single
source of truth); 60 cited shell paths resolve.

### 2.5 + 2.7-what-if (this commit)

**2.5 SHIPPED** — `cortex/plans.py` PlanCache: session-scoped PENDING
plan, tool-name composition LATER-WINS (the compound layer's own
rule), re-validated through the standard planner before any proposal,
commit only on successful apply, refused applies stay pending, explicit
discard ("never mind"/"start over"/"drop it"), bounded at 12 ops,
serialized through the session dict the bridge already round-trips.
Chat loop: compose on every PLAN turn (card shows the composed plan +
"composed with your pending plan (N ops total)"); explicit
"apply these changes" commits through the standard consent gate;
pending summary line after every card.

**2.7 what-if SHIPPED** — `settings/consequences.py`: five-edge cited
interaction table (transparency->blur, blur-inert, bar-scale 0.6
clamp, dodge-needs-persistent, padding floor), projection with
bounded derived effects, AC-3 domain check + INDUCED-value conflict
extension (user contradicts an edge's forced value -> cited conflict),
reversibility statement. Citation guard: every edge's cited file:line
re-verified against the checkout by test (claimed_content needle,
whitespace-squashed). Surfaces: settings --what-if TEXT|preset, chat
"what if [X]" turns (bare "what if" projects pending only), agent
engine validate_plan node (consent cards show consequences).

**Bugs found and fixed while building this**:
1. consequences.project() called optimize.check_conflicts with the
   wrong arity (single dict vs (ops, constraints)) — silently swallowed
   by try/except, so the AC-3 view NEVER fired; now correct + the
   induced-value extension per the proposal.
2. max_derived parameter accepted but never enforced — bounded now.
3. Step ops projected as raw deltas: "make the bar smaller" projected
   setBarScale=-1, firing the 0.6-floor edge + a false UNSUPPORTED
   conflict. All three projection sites (chat what-if, settings
   --what-if, engine validate_plan) now run over the planner's
   RESOLVED entries.
4. Bare "what if" routed the placeholder "show my pending changes" ->
   fuzzy match on "changed" -> setToastsChargingChanged composed into
   the pending plan. Bare what-if now projects pending only.
5. Latent chat-exit crash (PRE-EXISTING, verified by stash): near-
   threshold phrases logged the live _now() datetime raw into
   cortex_review; brain_state.save raised "Object of type datetime is
   not JSON serializable" at session end. Fixed by coercion at the
   log_review_candidate boundary; regression test pins clean exit.
6. edge citation line drift: dodgeEnabled is BarWrapper.qml:27 in
   current upstream (26 was contentWidth) — caught by the new
   citation-guard test, corrected.

54 new tests -> 1243 green; selfcheck + bash harness green.
Remaining: 2.7-dbus (dbus_surface.py per proposal), then 2.6 (registry
adapter + lexicon-diff + capability registration), then Phases 3-4.

### 2.7-dbus (this commit)

**SHIPPED** — `settings/dbus_surface.py`: the quarantined DBus surface
per proposals/2026-09-26-c-dbus-surface.md. Five-command catalog
(kwriteconfig6 x2, kscreen-doctor mode-from-observed-topology,
powerprofilesctl set-observed-profile, one IRREVERSIBLE dbus-send KWin
script unload), fixed argument arrays only, values from typed slots or
machine-derived from the read probes, per-command undo records
(kwrite: kreadconfig6 old value, type-coerced to round-trip
validation; kscreen: observed prior mode pair; power: prior active
profile; KWin: none, gated behind confirm_irreversible=True), one
inverse write per undo record. Kill-switch: capability dbus_surface
defaults OFF (file edit only). No NL request and no CLI write route
reaches it — plan_write (dry-run render, works while disabled) ->
consent -> run_write is the spine.

Quarantine: _QUARANTINED_IMPORTS grew to {pkgprobe.py,
dbus_surface.py} (schema_lint), pinned by tests in three suites
(agent, settings/safety, dbus's own). The belt-and-braces AST scans in
settings/tests/test_safety.py learned the quarantine so every other
module still fails on subprocess. Proposal status line updated to
IMPLEMENTED-behind-kill-switch (maintainer veto stays possible:
delete module + 2 carve-out lines). `import time` rejected by the
allow-list mid-build -> datetime.isoformat() timestamps (the tripwire
working as designed). 26 tests (fake subprocess.run; real-session
integration stays behind CAELESTIA_ASSIST_DBUS_TESTS=1, never in CI).

Suite: 1269 green; selfcheck + import policy clean. RATIONALE §16.
Remaining: 2.6 (registry adapter + lexicon-diff + capability
registration), then Phases 3-4.

### 2.6 (this commit) — Phase 2 COMPLETE

**Registry-generation adapter interface SHIPPED** —
`settings/gen_adapter.py`: the generation contract formalized.
canonical_bytes (the ONE serialization — every producer and comparison
goes through it, byte-identity is a pipeline property not a per-caller
convention); ADAPTERS registration table (pinned to the shipped
cpp-headers walker); verify_output_schema (structural check third-
party output must satisfy); verify() — the drift guard as a read-only
function (build, render, compare, first-diff-lines report, never
writes); CLI `python3 -m assistant.settings gen_adapter [--verify]`.
Committed tools.json verifies byte-identical through this seam (live).

**Signed lexicon-diff sharing SHIPPED** — `cortex/lexicon_diff.py` +
`cortex lexicon export|import|forget|list`: plain-text reviewable
diffs (newest 200, PII-stripped: no timestamps/paths/values), signing
OUTSIDE the assistant (minisign/sq/GPG over the canonical text — no
crypto code, no network, nothing can transmit). Import: caps + length
bounds + unknown-tool/unparseable/duplicate/over-cap rows as warned
no-ops (injection fuzz pinned), boosted-tools report, content-
addressed diff ids (sha256[:12]), one-command rollback (forget).
Landing: supervised pairs in A2's embedder seam (the shared singleton
reads persisted pairs at its lazy first build; absent import keeps
the corpus-only build byte-for-byte — the fingerprint test pins it)
+ review-bucket candidates for the learner's batch flow. Never touches
SYNONYMS. CLI round trip verified live (chat session -> export ->
import -> list -> forget).

**Capability registration SHIPPED** — `lexicon_sharing: True` (CLI-
only, offline, no network, explicit user command with rollback) in
the manifest, gated in the CLI; defaults-posture test updated.

Lint gap closed while building: check_import_policy's ast.Import
branch treated the ABSOLUTE intra-package form (import assistant.x.y)
as forbidden while allowing the from-form — both skip the assistant
root now (the target module is scanned by the same walk). Brain state
gained the CAELESTIA_BRAIN_STATE path override (same pattern as the
capability manifest) — tests/sandboxes never touch user runtime
state; a test-isolation leak in my own earlier chat tests (writing
the real sandbox state path) was found and fixed with it.

28 tests -> 1297 green; selfcheck + bash harness green. RATIONALE §17.
Phases 3 (maintenance audit) and 4 (version reset) next.

### Phase 3 — maintenance pass (this commit)

**3.1 Citations re-verified (live)** — all 277 tools' C++ declaration
lines against the checkout (test_registry, green); the interaction
edges' claimed_content needles against the checkout
(test_consequences, green); gen_adapter --verify: tools.json is
byte-identical to the cpp-headers adapter's output. GUARDS PROVEN to
fire: injecting `import subprocess` into plans.py failed selfcheck;
pointing the bar-scale edge citation at a wrong line failed the edge
guard. Both restored, both green.

**3.2 Consistency** — error style audited (uniform `error: ...` to
stderr, non-zero exit); dead imports removed (consequences: deque,
tool_by_path; dbus_surface: Sequence); dbus catalog_lines (exported,
unwired) now renders in the capabilities card when dbus_surface is on.

**3.3 Dev-process language cleaned from user-facing surfaces** —
README: "Issue #120 Phase 3"/"phase 3" milestone language replaced by
functional descriptions; hub.py --help docstring "(phase 1 routing
fix)" cleaned; cortex review/lexicon subcommand help strings cleaned.
Engineering docs (RATIONALE, WORKLOG, source comments) keep their
phase provenance deliberately — that is the audit trail.
Dead-code check: no dead functions across the phase 1-2 modules
(public, private, and __all__ exports all referenced; the chat
"try:" hint is a LIVE fallback pinned by its own test, not dead).

**3.4 Test coverage** — 1297 tests (baseline at session 1: 1049);
selfcheck + bash harness green; violation-catching proven live (above).

**3.5 Docs rewritten for coherence** — README: layer table extended
(genius 17 domains with the new algorithms, settings plan cache +
what-if, cortex LinUCB/Elo, agent archetypes + capability manifest),
new "conversational front door" section, safety contract gained the
two quarantined subprocess carve-outs disclosure + the no-auto-merge
rule, usage examples for chat/what-if/fsbrain/lexicon/capabilities,
test badge 922 -> 1297, gen_adapter --verify in Development.
RATIONALE: orphaned duplicate "## 5. Round three" essay (mis-
numbered, trailing) renumbered §18 and relocated before the closing
sections; stale "no commits, no branches" claim corrected to the
actual state (committed per-phase history, pushed to the fork);
known-gaps gained the live-notification-observation entry.
CHANGELOG rewrite is Phase 4 (the v0.1 collapse).

Suite 1297 green; selfcheck + bash harness green.

### Phase 4 — version reset to 0.1 (this commit)

CHANGELOG collapsed into a single "[0.1.0] — 2026-09-26 — initial
baseline" entry: the coherent system description (ten layers,
conversational surfaces, safety contract, 1297 tests green) — no
dev-process round/tier/phase milestones, no per-release history (the
git log IS the history; the changelog describes the release).
Version strings reset: pyproject.toml 0.7.0 -> 0.1.0,
assistant/__init__.py 0.3.0 -> 0.1.0, genius/__init__.py 1.0.0 ->
0.1.0. Git history NOT rewritten (verified: log + reflog show only
the per-phase commits, no rebase/amend); user runtime state NOT
touched (ledger, undo history, brain state, weights all live under
$HOME, none tracked in the repo — confirmed nothing in-tree was
modified by the reset).

Suite 1297 green; selfcheck green.

### Final summary — 2026-09-26 (session 2 completion)

**Definition of Done — ALL PHASES SHIPPED:**

- Phase 1 (routing fix): SHIPPED, commit 5043d9b — verbless front
  door, generalized inline delegation (all six categories), agent
  delegate, sidebar dispatch bridge; regression tests in
  test_cortex_pipeline / test_dispatch; output above.
- Phase 2: ALL SEVEN ITEMS SHIPPED — 2.1 fsbrain (1b51183), 2.2 new
  genius domains (7901ac4), 2.3 agent archetypes + capabilities
  (2e21af5), 2.4 self-learning (e11020b), 2.5 plan cache + 2.7 what-if
  (8d4468d), 2.7 dbus surface (df3d271), 2.6 lexicon-diff + generation
  adapter (13c1cfa). NONE BLOCKED.
- Phase 3 (maintenance audit): SHIPPED, 9771184 — citations
  re-verified live, guards proven to fire, consistency + dead-code
  audit, milestone language cleaned from user-facing surfaces, docs
  rewritten coherent.
- Phase 4 (version reset): SHIPPED, 09d522e — CHANGELOG collapsed to
  the single v0.1 initial baseline, all version strings reset to
  0.1.0, git history NOT rewritten, user runtime state NOT touched.

**Final verification (all run against HEAD 09d522e):**
- python3 -m unittest discover: **1297 tests, OK (skipped=1)**
  [baseline at session start: 1049]
- python3 -m assistant.hub selfcheck: **OK**
- bash tests/test_assistant.sh: **passed 10, failed 0**
- python3 -m assistant.settings gen_adapter --verify: **OK —
  tools.json byte-identical to the adapter's output**
- Count pins: 277 tools, group tallies, quarantine set, capability
  posture, genius domains — all pinned green.

**INVARIANT CHECK (the eight, each verified at HEAD):**
1. Python stdlib only in assistant/ core: HELD — ALLOWED_IMPORTS
   unchanged except the documented bz2 addition (2.2, named exception,
   cited); import policy clean (selfcheck).
2. No subprocess/socket/os.system in the default path: HELD — exactly
   two quarantined modules (pkgprobe, dbus_surface), both OFF by
   default behind capability kill-switches, pinned by tests in three
   suites; every other module zero-tolerance.
3. Every write: dry-run -> plan -> consent -> backup -> bounded undo:
   HELD — the applier spine unchanged; the plan cache composes but
   re-validates through the standard planner and the consent gate;
   dbus writes carry per-command undo records; no new write path
   exists outside the enumerated set.
4. No training/fine-tuning/embeddings; all intelligence is named
   classical algorithms with citations: HELD — LinUCB (Li et al.
   2010), feature hashing (Weinberger et al. 2009), BOCPD (Adams &
   MacKay 2007), Edmonds-Karp (1972), tabu search (Glover 1986),
   Elo/Bradley-Terry — all cited in docstrings and RATIONALE.
5. No resident daemon; event-driven; idle RSS ~0: HELD — one-shot
   CLI + bridge processes only; the fsbrain watcher finding (select()
   always ready, ctypes banned) documented as a known gap, no poller
   shipped; zero sleep-loops in the tree.
6. Registry/citation discipline: HELD — 277 tools' citations verified
   against the checkout; the interaction-edge table citation-guarded;
   byte-identity green; uncited claims remain lint errors.
7. No auto-merge of community/external data: HELD — lexicon import is
   an explicit, capped, warned, rollback-able user command; imports
   land as supervision and review candidates, never auto-applied.
8. OUT OF SCOPE stayed out: HELD — no OCR (screenshot diff is pixel
   hashing), no auto-execution above READ_ONLY without consent
   (agent nodes stay per-node consented; dbus run_write requires the
   caller's explicit consent), no federated auto-learning (sharing is
   reviewable text with external signing).

**Branch state:** 12 commits on main ahead of origin/main
(9a28465 -> 09d522e), 59 files changed, +10,031/-976. Working tree
clean. Issue #120 checked at session start (OPEN, 14 comments, last
updated 2026-09-25T17:34:30Z; snapshot's core facts still match).

---

## Session 2 — 2026-09-26 (Agent exponential-build — baseline)

Task ID: 0
Agent: ANI engineering agent (autonomous exponential-build run)

Scope of this session (fixed by the operating prompt; no phases beyond
it): Phase 1 unification layer (cortex/inbox.py, explain_unified.py,
diagnostics/fusion.py), Phase 2 NLU & resource governance
(dreamtime throttle, slot_tagger, lexicon trust, genius/units.py),
Phase 3 second-brain depth (personal/correlate.py, linkrec blend,
personal/selfcal.py), Phase 4 governance docs. One commit per
sub-item; branch `agent/exponential-build`; main untouched.

### Setup

- Fresh clone of `0x0nYx/caelestia-assistant` (HEAD `7d53b72`,
  branch `main`) into `/home/z/my-project/caelestia-assistant`.
- Branch `agent/exponential-build` created from main; main will not
  be committed to or merged by the agent.
- Read-only reference checkout: `ladybug-me/caelestia-kde` (shallow)
  at `/home/z/my-project/caelestia-kde`, needed only for the
  gen_adapter byte-identity verification.
- Read access confirmed to: assistant/genius/, assistant/cortex/,
  assistant/brain/, assistant/settings/, assistant/diagnostics/,
  assistant/agent/, assistant/scan/, assistant/brain/personal/.

### Baseline (before any change)

- Full suite: `python3 -m unittest discover -s . -p "test_*.py"`
  → **1297 tests, OK (skipped=12)**, ~57 s. (Session 1 ended at
  1297 OK skipped=1; two more skips are environmental — network/
  display-free suite, deltas noted per-phase as commits land.)
- `python3 -m assistant.hub selfcheck` → OK (rule schema valid,
  risk tiers consistent, import policy clean, settings lint rules
  valid).
- Registry byte-identity: `python3 -m assistant.settings.gen_adapter
  --verify --repo-root /home/z/my-project/caelestia-kde` → OK,
  tools.json byte-identical to the cpp-headers adapter output.
  NOTE on invocation: the operating prompt's literal command
  (`python3 -m assistant.settings gen_adapter --verify`) is not the
  recognized surface — the adapter's own module main is the entry
  (`python3 -m assistant.settings.gen_adapter --verify`), and this
  sandbox keeps the caelestia checkout outside the repo, hence the
  explicit --repo-root. Equivalent check, same guard.
- Grep-first pre-checks for Phases 1-3: no existing module named
  inbox.py / explain_unified.py / fusion.py / slot_tagger.py /
  units.py / correlate.py / selfcal.py anywhere in the tree — all
  seven new-file items are genuinely new; extension items
  (dreamtime.py, lexicon_diff.py, linkrec.py) will be re-checked
  in place at their sub-item.

### Plan for this session

Phase 1 first (highest leverage, lowest risk), then Phase 2, Phase 3,
Phase 4 docs; STOP conditions as written in the operating prompt; a
final WORKLOG summary entry lists every sub-item outcome.

### Phase 1.1 — unified pending-decisions inbox — SHIPPED

- Grep-first result: NO existing module aggregates the four decision
  sources (brain/service.py has ledger_list/ledger_decide but no
  join with gap clusters, the plan cache, or agent consents; brief
  compose() is a morning digest, not a decision surface). Genuinely
  new — built.
- New `assistant/cortex/inbox.py`: READ + DISPATCH layer over
  (1) `brain/ledger.py` pending proposals, (2) gap proposals —
  surfaced `ontology_gap` ledger items AND unproposed qualifying
  clusters previewed via `dispatch.cluster_gaps`, (3) the session
  pending-plan cache (`cortex/plans.py`, caller-owned payload file —
  no new session store), (4) the agent's per-node consent queue via
  `agent/engine.py`'s own simulate/consent_fn machinery.
- Ranking composes EXISTING values only: stated confidence (ledger /
  gap purity), the Beta-Binomial kind posterior from
  `brain/calibrate.acceptance_rate` (its own Beta(1,1) prior for
  unseen kinds), and the NamedBandit arm mean (`rank()`'s stable
  mean_estimate; the same class `cortex/learn.py` uses for its
  strategy bandit; arms keyed exactly as `settings_bridge.decide`
  rewards them — preset or `tool:<name>`). Score = stated x kind x
  arm, tie-broken (source, id): deterministic, nothing new computed.
- Dispatch goes to each source's OWN entry point: `Ledger.decide`;
  `dispatch.propose_gap_cluster` (NEW single-cluster entry point in
  dispatch.py, refactored out of `propose_gap_clusters` with
  byte-identical batch behavior — the inbox never files a proposal
  itself); plan ops re-validated by `settings.planner.plan` then
  handed to `settings.applier.apply` (dry-run preview by default;
  real write only behind the CLI's explicit `--write`;
  `PlanCache.commit` only after a real apply; reject = the cache's
  own TOTAL `discard`, stated out loud); agent decisions run
  `Agent.execute` with a consent_fn scripted to THAT node only (all
  other consent nodes refused) — or simulate-only without `--write`.
- Hub: `inbox` verb added (list/ranked/approve/reject; --json,
  --ledger/--state/--pending-plan/--goal/--file).
- Tests: `assistant/cortex/tests/test_inbox.py` — 25 cases: four-source
  aggregation, exact rank-input composition, deterministic ordering,
  per-source approve/reject dispatch (ledger via tmp fixtures, gap
  through the real dispatch entry point, plan with planner/applier
  mocked and payload asserted, agent with the consent gate scripted),
  honest refusals (unknown id/label/tool, missing target, agent
  without goal), and the no-write guarantees (unproposed-gap reject
  writes nothing; dry-run leaves the plan pending; reject never
  executes the agent graph).

### Phase 1.2 — unified `why` explainer — SHIPPED

- Grep-first result: `settings/explain.py` owns the settings read-only
  explanations; `genius/metacog.py` owns rule induction/clustering.
  No module walks back across engines — genuinely new, and neither
  existing explainer is touched.
- New `assistant/cortex/explain_unified.py`: ONE structured shape
  {engine, headline, lines, citations, confidence} for all five
  engines, every string lifted from the producing module's own output
  (templating, not synthesizing):
  * diagnostics -> `engine.diagnose`'s own verdict, rule id/title, fix
    lines, references, confidence;
  * cortex -> `dispatch.render_answer`'s own chat-card lines + the
    conformal calibrator's own reason/guarantee sentence for the
    route's score (its own "insufficient calibration data" honesty
    when there is no data);
  * settings -> `settings.explain.explain`'s own answer + cites +
    provenance hop strings when a ledger is available;
  * brain -> `calibrate.acceptance_rate`'s own posteriors over the
    ledger (per-kind rows + the calibration-note sentence shape);
  * wizard -> `settings.wizard.render` output byte-for-byte, headline
    from the winner's TOPSIS closeness.
- Walk-back: `why` (no id) explains the NEWEST ledger record (the last
  surfaced action with a durable record) through the engine its kind
  names (settings -> settings adapter with the diff's own file/calls;
  ontology_gap -> cortex; drift_* -> brain); `why <id>` accepts the
  inbox id space (ledger:/gap:/plan:/agent: — plan items render the
  cache's own summary() and contract line; agent items render the
  engine's own simulate "would" strings).
- Hub: `why` verb added. Read-only module: writes nothing anywhere.
- Tests: `assistant/cortex/tests/test_explain_unified.py` — 17 cases,
  one per source engine plus walk-back, consistent rendering, and CLI
  (wizard engine, last-action JSON, inbox-id).
- Flakiness note: one full-suite run during this sub-item reported a
  single failure that never reproduced across three subsequent full
  runs (buffered and unbuffered, 1339 OK each) and never surfaced a
  test name; recorded here rather than hidden.
