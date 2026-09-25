# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/)-flavoured.

## [Unreleased]

### Changed

- **License: MIT → GNU Affero General Public License v3.0** (the latest GNU
  AGPL version, 19 November 2007). Rationale: the assistant is a community
  project whose safety contract ("propose, never execute") only means
  something if every derivative — including one offered as a network service
  — remains equally inspectable. AGPLv3's remote-network-interaction clause
  (§13) closes the SaaS loophole that MIT leaves open. `pyproject.toml`
  metadata and classifiers updated; full license text in `LICENSE`.

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
