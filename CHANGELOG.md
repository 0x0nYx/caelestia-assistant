# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/)-flavoured.

## [Unreleased]

### Added — exponential-build-4

- Automatic log understanding: streaming Drain log-template mining (He, Zhu, He & Lyu, ICSM 2017) in `diagnostics/drain.py`, wired in front of the rule engine — a NO_MATCH/AMBIGUOUS diagnosis now templates the lines no signature matched (recurrence counts, caller-supplied first-seen dates, bounded capacity with honest overflow), rendered in `diagnose` reports and the `why` explainer with the explicit note that Drain clusters shapes, not causes.
- Deeper math/science: bounded symbolic integration (`mathengine.symbolic_integrate`, `genius calc --antiderivative`) — a pattern table over the existing AST (polynomial, exp, ln, trig, power-with-linear-inner), linear u-substitution with constant-ratio verification, integration by parts for `p(x)·{exp,sin,cos}` and `ln(x)` shapes, every antiderivative differentially verified at fixed sample points before shipping, honest `NO_CLOSED_FORM_IN_TABLE` verdicts (not a Risch algorithm); dual-number forward-mode automatic differentiation (`genius/autodiff.py`, Wengert 1964) with error-bar propagation for Group H; adaptive embedded Runge-Kutta 4(5) (Dormand & Prince 1980, `ode_solve --ode-method rk45 --tol`) with accepted/rejected step accounting; a bounded DPLL/CDCL-style SAT solver (`genius/sat.py` — unit propagation, pure literals, clause learning, hard node budget that ABSTAINs) with BMC reachability/deadlock auditing over finite-state graphs, wired as an additive audit into HTN goal decomposition (`agent/goals.py`) and the settings preset state graph (`settings/presets.py::transition_graph`).
- Personal knowledge graph depth: Brandes-betweenness bridge notes (`personal graph` / `bridges` — Freeman 1977, Burt 1992 brokerage framing: high betweenness, unremarkable PageRank/authority, gated on strictly positive betweenness; a different signal from the existing importance views, presented as such); windowed topic drift (`personal drift` — the EXISTING ADWIN + Page-Hinkley consensus reused verbatim on a binary "mix held" signal conditioned from consecutive NMF topic-mix cosine similarity on one shared basis; per-snapshot NMF bases would be unsound and were caught by the tests); cloze-deletion flashcard drafts (`personal cards` / `cards-decide` — mechanical blank selection, every draft in the mandatory approve/reject queue, FSRS scheduling only after approval); Murphy 1973 calibration decomposition (`personal selfcal` — REL/RES/UNC with the finite-sample covariance residual shown, never folded away).

### Added — exponential-build-3

- Reasoning primitives: Rete forward chaining over matched rules (Forgy 1982) and Dung abstract argumentation (1995) in `diagnostics/rette.py` / `argumentation.py`; Case-Based Reasoning cycle (retain = a ledger proposal) and structure-mapping analogy (Gentner 1983) in `retrieval/cbr.py` / `structure_mapping.py`.
- No-LLM learning: Kneser-Ney smoothed n-grams as the never-override SymSpell fallback (Kneser & Ney 1995; Chen & Goodman 1999) in `brain/kneser_ney.py`; ADWIN drift consensus with Page-Hinkley (Bifet & Gavaldà 2007) in `cortex/adwin.py`; hierarchical meta-bandit over recommendation engines (`brain/meta_bandit.py`); Laplace-DP lexicon-diff export (`cortex/dp.py`, `--dp` on `cortex lexicon export`).
- Program synthesis: `genius synth` scaled from 2-3 to 2-32 examples via version-space intersection (Gulwani 2011); Angluin L* regex induction (`genius/angluin.py`, 1987 — target mode never claims equivalence beyond its conformance set); macro capture/replay of APPROVED settings sequences (`settings/macros.py`; every replay needs `--apply` + `--confirm`, single-change macros included).
- Personal link-graph views: time-decay edge weights and edge-strength PageRank, HITS hubs/authorities (Kleinberg 1999), NMF topic extraction (Lee & Seung 1999) — `personal graph` / `personal topics`.
- Shell/system intelligence: PrefixSpan launch-sequence mining (Pei et al. 2001) with `launch_pattern` ledger proposals (`brain/sequences.py`); predictive battery/thermal advice (Holt 1957 trend + BOCPD regime change, iid-residual intervals labeled indications) via `cortex power`; inotify proactive triggering documented as a proposal only (`proposals/2026-09-27-c-inotify-proactive.md`).
- Community direction: signed rule packs (`rulepack export|import|...` — payload-hash integrity + the built-ins' own safety gates; imported packs are review data, never live); the synthetic-fixture framework `assistant/fixtures.py` (contributors need no caelestia-kde installation); opt-in engine telemetry (`cortex telemetry` — coverage/accuracy only, Laplace-DP export).
- Interaction polish: `settings --threeway` (current vs proposal vs undo-restore value per touched key); idle-cadence preference invitations (frequency-capped, surfaced in `settings --rank`, answered by `--prefer`); the ABSTAIN top-2 score gap in `caelestia-assist why`.

### Added — earlier builds (condensed)

- Unified pending-decisions inbox (`caelestia-assist inbox`) and unified `why` explainer; evidence fusion for troubleshooting (Genest & Zidek 1986); closed-loop resource throttle (PI cadence controller, `brain/dreamtime.py`); structured slot tagger (Collins 2002, conformal-gated); reputation-weighted lexicon trust (Kamvar et al. 2003, advisory only).
- Personal PKM: prediction calibration (Brier 1950, `personal/selfcal.py`), backlink blend (Adamic-Adar + TF-IDF), habit/completion correlation mining (Tate 1954, correlational-never-causal); dimensional/units algebra (`genius/units.py` — mismatched dimensions are errors, never coercions).
- Genius layer: inductive string synthesis, CSV expression domain (ast whitelist, eval never called), NCD file/folder resemblance, resolution syllogism checker (Robinson 1965), dimensional algebra, disk-backed bounded-memory search index (measured, not asserted, RAM), graphs/units/optimize/fsbrain-summary sidebar tools (read-only; A* stays CLI-only).
- Learning/audit: regret-vs-best-fixed audit (travels with its estimate caveat), off-policy evaluation gate (`brain ope`, IPS replay), attention-aware timing, hierarchical partial pooling (Efron & Morris 1975, flat-stays-flat), BOCPD drift on routing accuracy, undo-weighted calibration (PII-safe `quick` flag), pairwise re-ranker (conformal-gated, library-first), gap-cluster tool-template stubs, robust telemetry baseline (Leys et al. 2013).
- Governance docs: `docs/UPSTREAM_CASE.md`, `docs/LICENSING_OPEN_QUESTION.md` (left open), `docs/PR_SURFACE_PLAN.md`; commit-risk score (`devflow risk`, McCabe 1976).

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
