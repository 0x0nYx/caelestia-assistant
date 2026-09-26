# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/)-flavoured.

## [Unreleased]

- agent exponential-build: baseline recorded on branch
  `agent/exponential-build` before any feature work — 1,297 tests OK
  (skipped=12), `selfcheck` OK, gen_adapter byte-identity OK.
- Unified pending-decisions inbox: `caelestia-assist inbox
  list|ranked|approve|reject` — one ranked view over ledger proposals,
  gap clusters, the pending plan and agent consent nodes, dispatching
  every decision through each source module's own entry point (no new
  approval logic, no new write path; plan applies stay dry-run without
  `--write`).
- Unified `why` explainer: `caelestia-assist why [<id>|--engine ...]`
  walks back through whichever engine produced the last surfaced item
  (diagnostics rule citations, router path + conformal interval,
  settings consequences, brain posteriors, wizard AHP/TOPSIS) and
  renders each engine's own explanation output in one consistent
  shape — templated, never synthesized.
- Governance docs: `docs/UPSTREAM_CASE.md` (the classical-layer vs
  bundled-small-LLM argument, quoting the issue #120 corpus
  verbatim), `docs/LICENSING_OPEN_QUESTION.md` (the AGPLv3-vs-GPLv3
  upstream combination question, explicitly left open for a human),
  and `docs/PR_SURFACE_PLAN.md` (a proposed, not-executed narrowed
  upstream-first surface).
- Personal prediction calibration (`brain/personal/selfcal.py`): an
  opt-in Brier-score ledger (Brier 1950) over the user's own STATED
  predictions with explicit resolution — certainty claims rejected
  rather than clamped, double resolution refused, nothing inferred
  from unstated behavior; a distinct personal-only instance
  (brain/calibrate.py untouched).
- Backlink suggestion blend (`brain/personal/linkrec.py`): the
  Adamic-Adar graph signal combined with TF-IDF cosine similarity from
  the shared textmine engine (new public `tfidf_vectors`/`cosine`
  seam) on one saturated scale, with honest via labels and the
  minhash-Jaccard cold-start fallback retained.
- Habit/completion correlation mining
  (`brain/personal/correlate.py`): point-biserial (Tate 1954) and
  Yates-corrected chi-square tests between caller-supplied habit
  signals and task completion — framed correlational-never-causal,
  thin evidence labeled thin, missing signals skipped not imputed.
- Dimensional/units algebra (`genius/units.py`, wired into the genius
  dispatcher): SI unit parsing, prefixes, derived and accepted non-SI
  units, dimension-checked arithmetic and conversion — mismatched
  dimensions are an explicit error, never silently coerced; affine
  temperature converts but refuses arithmetic.
- Reputation-weighted lexicon trust (`cortex/lexicon_diff.py`): an
  EigenTrust-style advisory score (Kamvar et al. 2003) over each
  signer's keep/rollback history and boosted-tool overlap, shown at
  import time — strictly advisory: the explicit per-diff review
  requirement never auto-skips.
- Structured slot tagger (`cortex/slot_tagger.py`): an averaged
  structured perceptron (Collins 2002) layered ON TOP of the
  compositional slot grammar, trained only from local approved history
  through the grammar's own labels, gated by the conformal calibrator —
  low confidence or no calibration data falls back to the existing
  grammar/char-ngram path with the reason attached.
- Closed-loop resource throttle (brain/dreamtime.py): a PI cadence
  controller (anti-windup bounded, actuator-limited) reads the
  telemetry layer's read-only /proc+/sys snapshots during batch runs
  and holds the scan/brain cadence under a conservative, configurable
  CPU ceiling (default 25%, below the window-eligibility gate) —
  fixture-injectable telemetry, no new write path, no scheduler.
- Evidence fusion for troubleshooting (`diagnostics/fusion.py`):
  weighted-Bayes combination (log-odds opinion pool, Genest & Zidek
  1986) of the diagnostics rules', retrieval BM25's and scan's
  independently produced evidence into one ranked diagnosis with
  per-source contributions — read-only downstream consumer, abstains
  instead of inventing votes, rejects out-of-range inputs instead of
  clamping, merges hypotheses only through an explicit caller map.

## [0.1.0] — 2026-09-26 — initial baseline

The first release of the caelestia-assistant on-device intelligence
layer for [caelestia-kde](https://github.com/ladybug-me/caelestia-kde):
an offline-first, stdlib-only, no-training answer to issue #120 —
everything below ships together, as one reviewed baseline.

### The ten layers

- **Diagnostics** — deterministic rule engine over signature→fix
  mappings, every rule citing its source (file:line), reverse-joined
  to the settings tools that address each root cause; a read-only
  telemetry snapshot (/proc + /sys file reads only).
- **Retrieval** — BM25 over the repo's own docs and resolved issues;
  grounded answers, never invented ones.
- **Generative (optional)** — loopback-only single-attempt local
  Ollama call, sanitized output, OFF by default; no other network
  surface exists in the offline core.
- **Issue drafting** — structured templates → local file, never
  submitted.
- **Brain** — the classical-ML personal engine set (Naive Bayes,
  MinHash+LSH, SimHash, Isolation Forest, PageRank/label-propagation,
  knapsack + CPM day planning, Kaplan-Meier task survival, Holt/Kalman
  forecasts, FSRS-inspired spaced repetition, preference posteriors),
  with the personal-PKM tools split into an opt-in subpackage.
- **Cortex** — routing that learns: BM25+PPMI+char-ngram over the
  277-tool registry, AdaGrad online logistic, Thompson-sampling
  strategy bandit, Beta-Binomial calibration (surfaced honestly:
  "routes scored like this were right ~N% of the time"), episodic
  memory with user-settable Ebbinghaus decay, SVD/LSA and
  random-projection embedders (the measured winner is the default),
  a LinUCB contextual bandit (Li et al. 2010) for preset ranking, a
  shared Elo + Bradley-Terry pairwise primitive, and a
  session-scoped pending-plan cache that composes follow-up requests.
- **Settings (issue #120)** — natural language → validated plans over
  a 277-tool registry where every tool carries its C++ declaration
  citation, shipped Nexus control, and live QML reader; out-of-range
  values rejected (never clamped); preview-then-confirm applies with
  backup + bounded 12-entry undo; presets; compositional slot-grammar
  paraphrase recovery; optimization profiles (Pareto fronts,
  simulated-annealing and coordinate-descent synthesis, AC-3
  constraint propagation); a what-if consequence view over a cited
  cross-key interaction table (every edge re-verified against the
  checkout by test); and the registry-generation adapter interface
  (byte-identity guarded).
- **Genius** — 17-domain meta-router over stdlib engines: math,
  calculus, linear algebra, probability, logic/SAT/CSP (AC-3),
  decision analysis, graphs (Dijkstra/A*, Edmonds-Karp max-flow,
  label-propagation communities), optimization (branch-and-bound,
  tabu search, resource-contention scheduling), data (NCD
  compression similarity, BOCPD changepoints), text, palettes,
  system scans, shell history, and the filesystem second-brain
  (staleness scoring, SimHash near-dups, PageRank knowledge graph,
  byte-signature file typing).
- **Scan** — one-pass bounded-memory stream analysis: Aho-Corasick,
  Bloom, Count-Min, HyperLogLog, reservoir sampling, Page-Hinkley
  drift, SimHash fingerprints, opt-in novelty detection.
- **Agent** — HTN goal decomposition → DAG → simulate → per-node
  consent → observe & learn; five goal archetypes (config hygiene,
  package audit, log triage, notification triage, screenshot diff)
  behind a per-install capability manifest; never auto-consents.

### The conversational surfaces

- The verbless front door: `caelestia-assist "make my bar thinner"`
  routes free text one-shot; near-miss verbs get a "did you mean"
  prompt instead of an error.
- `caelestia-assist chat`: follow-ups compose against the pending
  plan (later instruction wins per tool, re-validated by the planner,
  refused applies stay pending, "never mind" discards); "what if"
  renders the consequence view before any consent; diagnosis, search,
  genius, brain, issue and agent-shaped requests answer inline.
- The in-shell AI sidebar (opt-in, user-keyed cloud tier) routes
  every prompt through the local cortex dispatcher first; only
  low-confidence requests hand off; every hand-off is a logged,
  clusterable local-ontology gap.
- Federated lexicon-diff sharing: `cortex lexicon
  export/import/forget` — reviewable text, signed and verified with
  the user's own external tools (minisign/sq/GPG), capped and warned
  on import, one-command rollback, no network code, no auto-merge.

### The safety contract (enforced by AST lint, pinned by tests)

- No executor imports (`subprocess`/`socket`/`ctypes`/… rejected by
  name) — with exactly two quarantined, kill-switched, fixed-argument
  carve-outs (the read-only package probe and the DBus surface), each
  pinned by test and OFF by default.
- Write paths enumerated: gated applier, proposal ledger, journaled
  tidy moves, learned-state JSON. Nothing else writes.
- Every write: dry-run → plan → consent → backup → bounded undo.
- No training, no embeddings, no auto-merge of external data; all
  intelligence is named classical algorithms with citations.
- Honest verdicts: AMBIGUOUS asks, ABSTAIN refuses, out-of-range
  rejects, thin evidence is labeled thin.

1,297 tests green; `selfcheck` and the registry byte-identity guard
green at release.
