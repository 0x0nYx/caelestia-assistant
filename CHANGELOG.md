# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/)-flavoured.

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
