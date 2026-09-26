# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/)-flavoured.

## [Unreleased]

### Added

- **Command execution gate for the AI sidebar (T2, prompt-injection
  closure).** A new `shell/services/CommandGate.qml` singleton gives the
  sidebar's other state-changing tools — `caelestia_command`, `open_app`,
  `set_timer` — the same validated gate the settings tools already had:
  a verified read-only allow-list (`caelestia version`, `caelestia help`,
  and the bare read forms `caelestia scheme list` / `scheme get`, each
  checked against upstream `src/bin/caelestia` @ dev, read 2026-09-26),
  a preview card showing the exact command verbatim, and explicit Apply /
  Cancel — nothing runs from raw model output. A state-changing command
  injected into a fetched webpage can now produce, at worst, a card the
  user ignores. `set_timer` now also reports its result at card-Apply
  time (and rejects non-positive durations instead of silently defaulting
  to 5 s); `open_app`'s launch pipeline moved behind the card unchanged.
  Static guards pin the gate's API, allow-list, wiring, card plumbing and
  bracket balance (`assistant/brain/tests/test_command_gate_qml.py`, 12
  tests).
- **Sidebar documentation (T1).** The README now has an "The in-shell AI
  sidebar" section documenting `shell/modules/sidebar/AiAssistant.qml` as
  the intentional, opt-in, user-keyed cloud chat tier — its providers,
  its keyring-stored keys, its read-only senses vs. gated actions
  boundary, and its fallback role relative to the offline core — which
  had shipped with zero README/CHANGELOG mention. The safety contract
  and CONTRIBUTING now state the two network carve-outs explicitly
  (loopback Ollama; the sidebar's user-initiated, user-keyed calls).

### Changed

- **Corrected the `caelestia_command` tool description to the verified
  upstream subcommand list.** The sidebar's system prompt advertised
  `shell, toggle, scheme, search, screenshot, record, clipboard, emoji,
  wallpaper, resizer, install, update`; the upstream CLI (fetched and
  read in full, 2026-09-26) implements `shell, install, update,
  wallpaper, scheme (list/get/set), screenshot, record, version, help`.
  The five phantom subcommands are gone, and the description now tells
  the model about the approval card.
- **`pyproject.toml` metadata (T3): version and description.** The
  version field was stale at 0.3.0 while the changelog shipped 0.7.0 —
  now aligned. The description now distinguishes the offline, no-LLM
  core (the `assistant/` Python package) from the optional in-shell
  cloud sidebar tier (`shell/`), one accurate sentence each, instead of
  claiming the whole project has no LLM surface.

### Changed (license)

- **License: MIT → GNU Affero General Public License v3.0** (the latest GNU
  AGPL version, 19 November 2007). Rationale: the assistant is a community
  project whose safety contract ("propose, never execute") only means
  something if every derivative — including one offered as a network service
  — remains equally inspectable. AGPLv3's remote-network-interaction clause
  (§13) closes the SaaS loophole that MIT leaves open. Combination basis
  (T4, stated for the record): GPLv3 §13 ("Use with the GNU Affero General
  Public License") explicitly permits a GPLv3 work to supplement its terms
  with AGPLv3 §13's remote-network-interaction condition, so this project
  stays combinable with the GPLv3 KDE ecosystem it lives in — the
  relicensing adds the network-service disclosure obligation without
  creating a new incompatibility. `pyproject.toml`
  metadata and classifiers updated; full license text in `LICENSE`.

## [0.7.0] — 2026-09-26

Issue #120 round four: Phase 4 — setup wizard, compound ordering, batch
active learning, and two grounded regression rules.

### Added

- **Setup wizard (`assistant/settings/wizard.py`, issue #120 phase 3
  "setup wizards")** — six pairwise tradeoff questions over four criteria
  (visual fidelity / battery / minimalism / performance) -> AHP weights
  (`genius/decision.py::ahp`, Saaty, consistency ratio reported) -> TOPSIS
  (`genius/decision.py::topsis`) over the five shipped presets scored by
  `optimize.score_plan` against the mapped objective profiles. The six
  questions (not "4-5") are deliberate: AHP's full-matrix reciprocity
  check makes C(4,2) the honest minimum; a spanning subset would need
  invented cells. Pure and write-free: the recommendation rides the
  ordinary `--preset` gate. `settings --wizard [--answers N,...]`.
- **Tool-dependency ordering (`assistant/cortex/compound.py::order_ops`,
  phase 4.2)** — a small declared precedence DAG (master toggle before
  dependent strength inside one subsystem: transparency/toasts/blur
  families, cited from the registry groups) applied via a stable Kahn
  topological sort with last-value dedup ("later clause wins" kept);
  wired into the pipeline before planning, so "disable transparency and
  set transparency base to 0.5" applies in the safe order.
- **Batch-curated active learning (`assistant/cortex/learn.py`,
  phase 4.3)** — near-threshold phrases (the router's own ABSTAIN
  min_score=0.30 / AMBIGUOUS min_margin=0.06 gates) are LOGGED into a
  bounded review bucket (state key `cortex_review`) by the chat loop
  instead of being silently absorbed online; the new
  `cortex review list|label INDEX SURFACE|dismiss INDEX` subcommand
  surfaces the batch: labeling teaches the learner (outcome "applied"
  for the named surface) and clears the candidate; dismissing just
  clears it. Nothing is learned without an explicit review decision.
- **Two grounded regression rules (`rules.d/known_regressions.json`,
  phase 4.4)** — (1) `CL-regression-ccache-629`: the installer's
  permanent system-wide ccache flip in /etc/makepkg.conf, cited to
  upstream issue #629 (closed 2026-09-06), verified against the issue
  body before writing. (2) `CL-regression-dualupdater-565`: the
  dual-updater state-desync symptom (Nexus pending-commit badge vs the
  real clone, uncommitted edits overwritten by the shadow clone), cited
  to upstream issue **#565** (OPEN). Corpus docs ISS-629.md and ISS-565.md
  added and the committed BM25 index rebuilt.

### Flagged (mission deviation, in the open)

- **The mission's "#818" reference for the dual-updater bug is wrong.**
  Upstream issue #818 is "CAELESTIA-KDE OVERHAUL" — a PR-template issue
  with no updater content (fetched and read 2026-09-26). The actual,
  verified dual-updater state-desync issue is **#565** ("Two independent
  update mechanisms share version-tracking state but pull from different
  repo checkouts", still open). The rule cites #565 and fingerprints the
  PRE-fix symptom exactly as the mission intended; inventing an #818
  citation would have violated the every-claim-verifiable rule.

### Tests

- 811 → **827** unittests, all green
  (`cortex/tests/test_issue120_phase4.py`: wizard determinism +
  consistency flagging + honest battery-preset ranking expectation +
  off-scale rejection, master-before-strength ordering + spoken-order
  preservation + last-value dedup + pipeline wiring, near-threshold
  logging (never silently learned), dedup/bounding, label-teaches-
  learner, CLI list/dismiss, and the router's real threshold constants
  pinned).

## [0.6.0] — 2026-09-26

Issue #120 round three: Phase 3 — telemetry-grounded features, on-demand
only.

### Added

- **Read-only telemetry probes (`assistant/diagnostics/telemetry.py`)** —
  plain pathlib/glob reads of /proc/loadavg, /proc/meminfo,
  /sys/class/power_supply/*/capacity and /sys/class/thermal/*/temp, the
  same file-probe precedent Layer 1 already uses. On-demand only: every
  call is one snapshot (the `telemetry_snapshot` bridge op and the module's
  own `main()` exist for diagnostic/report/dreamtime callers); there is no
  daemon and no poller. Missing interfaces report
  `{"available": false}` — honestly unavailable, never a fake number.
  Tests run against fixture proc/sys trees, never the live kernel.
- **Battery-aware secondary preset reward (Phase 3.2)** —
  `NamedBandit.reward(name, approved, secondary=None)` accepts an optional
  [0, 1] signal computed from battery drain-rate deltas
  (`telemetry.drain_rate_percent_per_hour` + `reward_from_drain_delta`);
  it contributes fractional Beta pseudo-counts at weight 0.25 so it can
  never outweigh one real approve/reject decision, and is byte-identical
  to the old update when None. Plumbed through `settings_bridge.decide`,
  `brain settings decide --battery-reward R`, and the settings decide
  service path. Existing preset_bandit tests pass unmodified.
- **Startup-time regression detection (Phase 3.3)** —
  `genius/data.py::startup_regressions(series, timestamps, labels)`
  feeds a caller-supplied boot-time series into the EXISTING two-sided
  CUSUM (`changepoints`, no duplicate detector) and classifies each
  changepoint as regression/improvement/level-shift at a 15% mean delta.
  Dates/versions come only from the caller's input
  (`genius data --startup-regressions --series ... --stamps ... --versions ...`).

### Tests

- 795 → **811** unittests, all green
  (`diagnostics/tests/test_telemetry_battery_startup.py`: fixture-based
  probes + honest unavailability, drain-rate math and its [0,1] mapping,
  secondary-reward no-op/dominance/ranking-shift properties, bridge
  plumbing, CUSUM index stability + honest interpretation).

## [0.5.0] — 2026-09-26

Issue #120 round two: Phase 2 — workspace, monitor topology, appearance,
accessibility.

### Added

- **Workspace profiles (`assistant/brain/workspace.py`, issue #120 Phase 3
  "workspace profiles")** — k-means (k-means++ seeded, reusing
  `genius/data.py::kmeans`) over (app, workspace, monitor, hour-of-day)
  session vectors with circular hour encoding; clusters pass a
  cluster-purity + minimum-support filter before becoming named
  `workspace_profile` LEDGER PROPOSALS. Data-source honesty: the upstream
  shell persists no session log (the workspace-tracker effect broadcasts
  live state only; verified in the caelestia-kde tree before writing this),
  so sessions arrive caller-supplied — no invented schema. Surfaced as
  `brain workspace SESSIONS.json [--propose]` and the `workspace_profiles`
  bridge op.
- **Per-monitor-topology memory (`assistant/brain/topology.py`)** — sha256
  fingerprint over the per-monitor override directory set (the layout the
  shell's own config loader maintains); deltas (non-default, non-global
  registry leaves) are remembered per hash in the brain state file, and a
  topology change that matches remembered memory emits ONE
  `topology_restore` ledger proposal — never auto-applied.
  `brain topology [--propose]` + `topology_observe` bridge op.
- **Idle-state throttling rule (`assistant/diagnostics/rules.d/
  idle_throttle.json`)** — deterministic rule matching idle/overnight
  battery-drain complaints; its fix steps propose the shipped battery-saver
  preset's exact tool calls (setBlurEnabled/setAnimationSpeed) as a
  ledger throttle + revert pair, with a plain-file probe clarify probe.
  Round-trip propose→approve→revert→approve pinned by test through
  settings_bridge.
- **Wallpaper palette extraction (`assistant/genius/palette_extract.py`)** —
  k-means color quantization in OKLab over wallpaper pixels (minimal stdlib
  PNG reader: zlib+struct, deterministic stride sampling); accent
  selection = highest-chroma cluster among clusters with pixel share
  >= 0.15; WCAG contrast verdicts included. Surfaced through the EXISTING
  inert scheme-suggestion path: `settings --wallpaper-palette PATH`
  renders via the same SUGGESTED verdict and SUGGESTED_NOT_EXECUTED lines
  the parser uses for accent-color requests — no new suggestion mechanism.
- **Scheme accessibility audit (same module, Phase 2.5)** — all pairwise
  text/background WCAG contrast with failing pairs flagged at AA (4.5:1);
  protanopia/deuteranopia/tritanopia simulation via the Viénot-Brettel-
  Mollon (1999) linear-RGB matrices; nearest compliant color via bounded
  bisection on the OKLab L axis (hue/chroma preserved) with an honest
  failure verdict when the hue cannot reach the target.
- **Shell-event rhythm (Phase 2.6)** — `brain rhythm --settings-file FILE
  [--scheme-switches ...]` feeds the unchanged rhythm engine from
  settings-apply history + ledger decision stamps (+ caller-supplied
  scheme-switch timestamps, since the scheme system persists no switch
  history — verified upstream). Existing rhythm tests untouched.

### Changed

- ALLOWED_IMPORTS.txt: `struct` added with rationale (pure binary
  pack/parse for the PNG reader). `shutil` remains forbidden and unused.

### Tests

- 775 → **795** unittests, all green (`brain/tests/test_issue120_phase2.py`:
  20 tests covering the correct cluster proposed and nothing auto-applied,
  noise never becoming a profile, two topology hashes with asserted deltas,
  the observe→remember→propose round-trip, rule load+match, the idle
  throttle propose/revert round-trip, synthetic-wallpaper extraction, the
  documented failing pair caught, dichromacy mapping, compliant repair +
  honest failure, and shell-event rhythm surfacing).

## [0.4.0] — 2026-09-26

Issue #120 round one: the Directive-0 scope split plus Phase 1 (config
health, pre-write sanity, multi-hop provenance).

### Added

- **Directive 0 — brain scope split.** The personal-knowledge-management
  engines (`vault`, `graph`, `srs`, `survival`, `journal`, `ghost`,
  `linkrec`, `health`, `planner`, `duration`, `priority`) moved to
  `assistant/brain/personal/` behind their own entry point
  (`python3 -m assistant.brain.personal`) with a separate README stating
  they are NOT part of the #120 feature surface. The brain root and the
  JSON bridge keep only shell-native surface (ledger, settings bridge,
  prefs, rhythm/forecast/anomaly, placement, calibration, drift, tidy,
  brief, dreamtime). The single root→personal import is `dreamtime`
  reusing the `planner.knapsack` engine (documented in both READMEs).
  Generic utility libraries (`nlp`, `minhash`, `naive_bayes`, `textmine`,
  `spellfix`) stay in root per the reuse contract. Top-level README module
  table flags the split.
- **Config health linter (`assistant/settings/lint.py`)** — deterministic
  rule engine over shell.json: unknown keys (not a tool path and not in
  the not_exposed table), out-of-range/mistyped values vs the shipped
  control ranges, the blur-without-transparency silent no-op (grounded in
  the registry's own explain rule, BlurOffsets.qml:17), and inert
  customizations behind a disabled master switch. Wired as a read-only
  `settings --lint` flag and into `selfcheck` (rule-table validation is
  enforced; user-config findings are informational only).
- **Pre-write sanity simulator (`assistant/settings/sanity.py` + applier
  hook)** — deterministic checks over the POST-apply state before any byte
  is written, including single-setting applies: WCAG 2.5.8 tap-target
  warning for projected `bar.dock.iconSize` < 24px (warning, not refusal —
  the shipped 16–96 range and the `minimal` preset stay authoritative), and
  WCAG 1.4.3 AA projected-contrast REFUSAL via
  `genius/creative.py::contrast_ratio` when the caller supplies scheme
  colors (without scheme context the check honestly reports itself skipped
  — shell.json carries no color leaves). A refused apply leaves target,
  backup and undo history byte-identical. `write=True` gate semantics
  unchanged.
- **Multi-hop `--explain` provenance (`assistant/settings/explain.py`)** —
  read-only backward walk: current value ← which apply set it (undo
  history) ← which ledger proposal/preset produced that apply ← that
  preset's approval estimate for this user (preset bandit Beta posterior).
  Stops at the first ledger entry or 5 hops. Rendered under `--explain`
  when ledger/state files exist; missing sources simply shorten the chain.

### Fixed

- `cortex suggest --apply` crashed on `brain_ledger.load()/save()` (which
  do not exist); it now uses `Ledger(DEFAULT_LEDGER)` and honestly reports
  a blocked/no-op dry-run instead of creating a phantom proposal.

### Tests

- 751 → **775** unittests, all green: `settings/tests/
  test_lint_sanity_provenance.py` (18 tests: known-bad fixture lint
  findings, clean-config zero findings, contrast refusal with a
  byte-identical directory snapshot, tap-target warning, honest
  contrast-skip note, full provenance chain, stop rules, read-only
  guarantees) and `brain/personal/tests/` (moved PKM coverage), plus
  bridge-surface pins asserting the personal ops are gone from the shell
  bridge. No import-policy changes were needed (`copy` avoided via a JSON
  round-trip deep copy; nothing added to ALLOWED_IMPORTS.txt).

## [0.3.0] — 2026-09-25

The "second brain" release: the assistant stops being five troubleshooting
layers and becomes an agent with memory, preferences, and bounded autonomy —
while keeping the no-LLM, stdlib-only, never-execute contract.

### Added

- **Agent layer (`assistant/agent/`)** — HTN-style goal decomposition into
  dependency-ordered task graphs over every layer; simulate-before-execute
  projection; per-node consent gate (refused nodes skip dependents); outcome
  observation into the learners; 20-questions clarification via expected
  information gain (`--questions`).
- **Stream intelligence (`assistant/scan/`)** — one-pass bounded-memory
  scanning of huge logs: Aho-Corasick multi-pattern automaton, Bloom-filter
  line dedup, Count-Min Sketch token frequencies, HyperLogLog distinct
  counting, reservoir sampling, EWMA rates + Page-Hinkley rate-change alarm.
- **Settings optimizer (`assistant/settings/optimize.py`)** — issue #120
  Phase 3: five objective profiles (gaming/battery/minimal/comfort/
  accessibility) over the 277-tool registry, Pareto-frontier analysis,
  simulated-annealing & coordinate-descent preset synthesis, AC-3 constraint
  propagation that refuses contradictory requests with reasons.
- **Brain round three** — `prefs.py` (Beta-posterior preference model with
  exact binomial CDF credible intervals, learned from ledger decisions),
  `tidy.py` (journaled, collision-safe, rollback-able filesystem
  organization; never deletes), `brief.py` (the deterministic daily brief).
- **Cortex honesty upgrades** — `conformal.py`: split-conformal route
  verdicts (distribution-free coverage guarantee), query-by-committee active
  learning, Page-Hinkley acceptance-rate drift detector with latch + reset.
- **Genius round two** — `graphs.py` (Dijkstra, A*, Kahn toposort, longest
  DAG path/critical path, union-find, Kruskal MST, Bellman-Ford with
  negative-cycle reporting, Tarjan articulation points, Hungarian/JV optimal
  assignment) and `optimize.py` (simulated annealing, hill-climbing with
  restarts, steady-state genetic algorithm, ternary + golden-section search,
  Pareto frontiers); exposed as `genius graphs` / `genius optimize` verbs.
- **JSON bridge ops** for all of the above (`agent_plan`, `agent_simulate`,
  `scan_text`, `brief`, `tidy_survey`, `optimize_recommend`,
  `optimize_score`, `prefs_report`, `conformal_verdict`).
- Hub routes: `agent`, `scan`, `brief`, `tidy`; brain subcommands `brief`,
  `tidy`, `prefs`.
- Community packaging: root README, MIT LICENSE, this changelog,
  CONTRIBUTING.md, pyproject.toml, GitHub Actions CI, repaired
  `tests/helpers.sh` shell harness.

### Fixed

- `assistant/generative` imports no longer break under
  `unittest discover -s assistant` (alternate discovery roots).
- `tests/test_assistant.sh` referenced a missing `helpers.sh`.

### Tests

- 639 → **751** unittests, all green; import-policy AST lint extended to the
  new packages (`heapq`, `zlib` added to the allow-list with rationale).

## [0.2.0] — earlier

- Settings layer for issue #120: 277-tool cited registry, frozen 18-tool
  grammar parser, planner validation, gated applier, explainability, bounded
  undo, presets, in-shell QML SettingsTools service (byte-identity-tested).
- Cortex learned-routing layer (BM25+PPMI+char-ngram, AdaGrad, Thompson
  strategy bandit, Beta calibration, episodic memory, co-change lift).
- Brain layer (24 classical-ML modules), genius universal intelligence layer
  (16 domains), diagnostics/retrieval/generative/issues pipeline.

## [0.1.0] — initial

- Layer 1 deterministic diagnostics, Layer 2 offline retrieval, optional
  loopback-only generative layer, issue drafting. Stdlib-only import policy
  enforced by AST lint.
