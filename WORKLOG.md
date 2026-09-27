# WORKLOG — caelestia-assistant engineering record

One section per build. Condensed in exponential-build-3 Phase 2 to
the engineering substance — deliverables with commits, judgment
calls, honest findings, final verification — per the build's
de-redundancy pass; the session-by-session process narrative lives
in git history.

---

## Build 1 — 2026-09-26 — initial layer + v0.1.0 reset

Scope (per the operating prompt): routing fix, seven Phase-2 feature
items, a maintenance audit, and the version reset to 0.1.0.

Delivered (12 commits on main, 9a28465 → 09d522e):

- Routing fix (5043d9b): verbless front door, generalized inline
  delegation (all six categories), agent delegate, sidebar dispatch
  bridge.
- 2.1 fsbrain (1b51183); 2.2 new genius domains (7901ac4, incl. the
  documented bz2 allow-list addition); 2.3 agent archetypes +
  capabilities manifest (2e21af5); 2.4 self-learning (e11020b);
  2.5 plan cache + 2.7 what-if (8d4468d); 2.7-dbus surface
  (df3d271, quarantined + OFF by default); 2.6 lexicon-diff +
  gen_adapter (13c1cfa).
- Maintenance audit (9771184): citations re-verified live against the
  upstream checkout, guards proven to fire, dead-code and consistency
  audit, user-facing milestone language cleaned.
- Version reset (09d522e): CHANGELOG collapsed to the single v0.1.0
  baseline entry; history NOT rewritten; runtime state untouched.

Honest findings kept: the fsbrain watcher gap (select() always ready,
ctypes banned — no poller shipped); the corpus snapshot of issue
#120 lagging the live issue (re-verified before citing). Final
verification: 1297 tests OK (baseline 1049), selfcheck OK, bash
tests 10/0, gen_adapter byte-identical; the eight invariants HELD
(details in git history).

## Build 2 — 2026-09-26 — exponential-build (unification layer)

Scope: Phase 1 unification, Phase 2 NLU/resource governance, Phase 3
second-brain depth, Phase 4 governance docs. Branch
`agent/exponential-build`, merged via PR #1.

Delivered (15 commits):

- Unified pending-decisions inbox (`cortex/inbox.py`): one ranked
  view over ledger proposals, gap clusters, the pending plan and
  agent consents — dispatching through each source's own entry
  point; no new approval logic, no new write path.
- Unified `why` (`cortex/explain_unified.py`): walks back through
  whichever engine produced the last surfaced item; templated, never
  synthesized.
- Evidence fusion (`diagnostics/fusion.py`): log-odds opinion pool
  (Genest & Zidek 1986) over rules/BM25/scan evidence; abstains
  rather than inventing votes.
- Closed-loop resource throttle (`brain/dreamtime.py`): PI cadence
  controller (Åström & Hägglund-style anti-windup, actuator-limited)
  under a 25% CPU ceiling; fixture-injectable telemetry.
- Structured slot tagger (`cortex/slot_tagger.py`): averaged
  structured perceptron (Collins 2002) on top of the slot grammar,
  conformal-gated, grammar fallback with the reason attached.
- Reputation-weighted lexicon trust (`cortex/lexicon_diff.py`):
  EigenTrust-style advisory score (Kamvar et al. 2003) over signer
  keep/rollback history; advisory only, review never auto-skips.
- Personal PKM depth: prediction calibration (`personal/selfcal.py`,
  Brier 1950, certainty claims rejected not clamped), backlink
  blend (`personal/linkrec.py`, Adamic-Adar + TF-IDF cosine on one
  saturated scale), habit/completion correlation mining
  (`personal/correlate.py`, point-biserial Tate 1954 + Yates
  chi-square, correlational-never-causal).
- Dimensional/units algebra (`genius/units.py`): SI + derived +
  accepted non-SI, dimension-checked arithmetic (mismatch is an
  error, never a coercion; affine temperature converts but refuses
  arithmetic).
- Governance docs: `docs/UPSTREAM_CASE.md`,
  `docs/LICENSING_OPEN_QUESTION.md` (left open for a human),
  `docs/PR_SURFACE_PLAN.md`.

Final verification: 1433 tests OK (baseline 1297), selfcheck OK,
gen_adapter byte-identical; the eight invariants HELD. One documented
1.2-flake (never reproduced, recorded honestly).

## Build 3 — 2026-09-27 — exponential-build-2 (21 sub-items)

Scope: a fixed 21-sub-item backlog across cortex/brain/genius/
retrieval/diagnostics + two governance addenda. Branch
`agent/exponential-build-2`, merged via PR #2.

Delivered (22 commits) — each sub-item with its commit:
1.1 gap-cluster tool-template stubs `cortex gaps --draft-stubs`
(0e0d4e1); 1.2 undo-weighted calibration, PII-safe `quick` flag,
QUICK_UNDO_WEIGHT=4.0 (153b84a); 1.3 BOCPD drift on hit-rate
(eee8517); 1.4 pairwise re-ranker, Rosenblatt 1958 / Herbrich et al.
2000 / Collins 2002, conformal-gated, library-first (d20bb0b); 2.1
inductive synthesis `genius synth`, Gulwani 2011 (58c0fc6); 2.2 CSV
expression domain, ast whitelist, eval never called (7537506); 2.3
NCD resemblance `fsbrain resemble` (18f9745); 2.4 resolution
syllogism checker, Robinson 1965 (b5e564d); 2.5 commit-risk score,
McCabe 1976 × recency-decayed churn (f9cef0a); 2.6 robust
Mahalanobis baseline, Leys et al. 2013 (38111e0); 3.1 hierarchical
partial pooling, Efron & Morris 1975, method-of-moments, flat-stays-
flat (ef84c5e); 3.2 off-policy evaluation gate `brain ope`, IPS
replay with support/coverage (a05d5c4); 3.3 regret-vs-best-fixed
audit (9476289); 3.4 attention-aware timing, Thompson over buckets
from the pooled prior (10e56b2); 4.1 disk-backed search index,
external merge sort, MEASURED VmHWM (b3ddc58); 5.1-5.4 sidebar tools
genius_graphs (58fc36a + allow-list fix 3593e31), genius_units
(26e4927), genius_optimize (3c36126), genius_fsbrain_summary
(cdd94e4); 6.1/6.2 governance addenda (9b38ec2).

Honest findings kept: the disk-index report prints an unflattering
process-level RAM number rather than asserting the ceiling held; A*
stays CLI-only (heuristic is code, not data); irregular plurals stay
honestly distinct in the syllogism checker. Two process incidents
fixed forward: a chained push that ignored the suite's exit code
(gated SUITE_EXIT=0 thereafter), and a commit that landed before the
allow-list suite ran (the guard worked; ordering was the failure).
Final verification: 1622 tests OK (baseline 1433), selfcheck OK,
gen_adapter byte-identical, bash tests 10/0; the eight invariants
HELD.

## Build 4 — 2026-09-27 — exponential-build-3 (this build)

Scope: seven feature groups (A reasoning primitives, B no-LLM
learning, C program synthesis, D second-brain graph views, E shell/
system intelligence, F community direction, G interaction polish),
then de-redundancy, adversarial verification, and the v0.1.0-baseline
history reset. Branch `agent/exponential-build-3`; baseline archived
at tag `pre-v0.1-reset-3-archive` before any change (1622 tests OK,
skipped=12, selfcheck clean).

Delivered (9 feature commits, ac547a5 → 2e4a9d7):

- A (diagnostics/retrieval): Rete forward chaining (Forgy 1982) +
  Dung argumentation (1995) over matched rules (ac547a5); CBR cycle
  (retrieve→reuse→revise→retain, retain = a ledger proposal) +
  structure-mapping analogy (Gentner 1983) (c56f729).
- B (brain/cortex): Kneser-Ney smoothed n-grams as the SymSpell
  fallback signal (Kneser & Ney 1995 / Chen & Goodman 1999) + ADWIN
  drift consensus with Page-Hinkley (Bifet & Gavaldà 2007)
  (d19a67e); hierarchical meta-bandit over the recommendation
  engines (Thompson sampling per Chapelle & Li 2011, pooling reuse,
  regret audit reuse) + Laplace-DP lexicon-diff export (Dwork et al.
  2006; noised-evidence DP, row presence exact) (8489afe).
- C (genius/settings): synth rewritten from 2-3-example enumeration
  to version-space intersection (Gulwani 2011; 2..32 examples,
  arithmetic ambiguity counts, hard budgets that refuse fast);
  Angluin L* regex induction (1987; TARGET mode with a
  sound-but-incomplete conformance oracle, EXAMPLES mode the
  canonical consistent quotient); macro capture/replay of APPROVED
  settings sequences (Cypher (ed.) 1993 pattern; stored inside the
  history file per the A3 precedent; every replay re-consented,
  single-change macros included) (2087d09).
- D (brain/personal): time-decay edge weights + edge-strength
  PageRank with teleport slack (the per-source-renormalized
  formulation provably cancels decay — the flaw the shipped form
  exists to avoid), HITS hubs/authorities (Kleinberg 1999; the
  3-node graph's golden-section fixed point is the test oracle),
  NMF topic extraction (Lee & Seung 1999; sparse-V + Frobenius-
  identity error, 5x faster than dense) (37024ad).
- E: PrefixSpan launch sequences (Pei et al. 2001; day-support,
  launch_pattern ledger proposals); predictive battery/thermal
  advisor (Holt 1957 + BOCPD over differences with a pre-shift
  baseline variance — the whole-series default is contaminated by
  the shift it should reveal — and a 1°C² thermal floor where a
  sharper floor underflows and MISSES gross shifts; iid-residual
  intervals labeled indications); inotify proactive triggering =
  DESIGN DOC ONLY (proposals/2026-09-27-c-inotify-proactive.md,
  three shapes ranked, none implemented) (733b4f7).
- F: signed rule packs (canonical bytes + payload-sha256 integrity +
  the same forbidden-key safety gates the built-ins pass; imported
  packs are review data, never live; signing stays in the user's
  external tool); the synthetic-fixture framework
  (assistant/fixtures.py + CONTRIBUTING section — contributors need
  no caelestia-kde installation); opt-in engine telemetry
  (coverage/accuracy only, Laplace-DP export riding the B4
  mechanism, capability-gated) (0118639).
- G: `settings --threeway` (file-now vs proposal vs undo-restore,
  with the apply-then-undo honesty note); idle-cadence preference
  invitations (frequency-capped: one pending, 7-day spacing, 14-day
  expiry; fewest-comparisons + closest-Elo pair selection; surfaced
  in --rank, consumed by --prefer); ABSTAIN top-2 score gap in the
  unified explainer (2e4a9d7).

Honest findings kept: B3 ships library-first (no live wiring — no
dead report line); the L* conformance oracle never claims equality
(pinned at its divergence); CONTRADICTIONS/the CBR adaptation table
ship honestly empty (no verified data); the advisor's interval is an
iid-residual indication, not a calibrated interval; the meta-bandit
regret estimate is context-contamination-optimistic (the caveat
travels on every report). Final verification: 1987 tests OK
(skipped=12; baseline 1622, +365), selfcheck OK across every
commit.

## 2026-09-28 — branch unification (single-branch main)

Per the operator's directive, all work now lives directly on main.
agent/exponential-build-3 was merged into main (9562987, merge of
unrelated histories; the content diff is empty — the v0.1.0 baseline
snapshot 50cddea and the build-3 tip e861861 had identical trees), so
main now carries the complete history: the original repo history,
builds 1–2 (via PRs #1/#2), the eleven build-3 commits, and the v0.1.0
baseline snapshot. The agent/exponential-build-3 branch was then
retired (deleted, remote and local) — its tip is an ancestor of the
merge commit, so nothing was lost. Archive tags kept:
pre-v0.1-reset-3-archive (cf2eb6b) and v0.1.0-baseline-3 (50cddea).
Verification on the unified main: 1987 tests OK (skipped=12),
selfcheck OK, bash tests 10/0.

---

## Build 5 — 2026-09-28 — exponential-build-4 (this build)

Scope (per the operating prompt): eight feature groups — A automatic
log understanding, B deeper math/science, C personal knowledge-graph
depth, D self-learning upgrades, E system/OS intelligence, F NLU
depth, G community distribution, H honesty/uncertainty hardening —
then Phase 2 de-redundancy + adversarial verification, and the
baseline reset. Branch `agent/exponential-build-4`; baseline archived
at tag `pre-v0.1-reset-4-archive` (commit 6cafdfa) before any change:
1987 tests OK (skipped=12), selfcheck OK.

Delivered (9 commits on the branch, fa53118 → 560789e):

- A Drain (fa53118): streaming fixed-depth parse-tree template miner
  (He, Zhu, He & Lyu, ICSM 2017) in `diagnostics/drain.py`, wired in
  front of the rule engine — NO_MATCH/AMBIGUOUS diagnoses template
  the lines no signature matched; bounded memory with honest
  overflow; shapes-not-causes note carried into the report and `why`.
- B math/science (9bc93c6): bounded symbolic integration
  (`mathengine.symbolic_integrate` — table + linear u-substitution +
  integration by parts; every antiderivative differentially verified
  at fixed points before shipping; honest NO_CLOSED_FORM_IN_TABLE,
  not Risch); dual-number forward-mode AD (`genius/autodiff.py`,
  Wengert 1964); adaptive Dormand-Prince 4(5) in ode_solve;
  DPLL/CDCL-style SAT with a hard ABSTAIN budget (`genius/sat.py`)
  and BMC reachability/deadlock auditing wired into HTN decomposition
  and the preset state graph.
- C personal graph depth (c348c92): Brandes betweenness + bridge
  notes (Freeman 1977 / Burt 1992); windowed topic drift reusing the
  ADWIN+Page-Hinkley consensus verbatim on a shared-basis signal;
  cloze flashcard drafts behind the mandatory review gate; Murphy
  1973 calibration decomposition with the finite-sample residual
  shown.
- D self-learning (b3e407b): conservative bandits (Wu et al., ICML
  2016) gating the strategy bandit's own Thompson sample; Learn++.NSE
  (Elwell & Polikar 2011) as the selectable smooth-drift alternative;
  Wolpert stacked generalization as drop-in fusion weights.
- E system intelligence (f5f4689): steady-state Kalman failure
  horizons over the telemetry series (`diagnostics/forecast.py`);
  package_breakage deepening the audit archetype with the shipped
  graph engines (no second package path); Merkle config-tree diffing
  (`brain/merkle.py`).
- F NLU depth (07e4a22): linear-chain CRF slot tagger
  (Lafferty et al. 2001) selectable and conformal-gated beside the
  perceptron; Hobbs 1978 coreference discipline wired into the
  pending-plan composer.
- G community distribution (33b2ba5): DP-noised cold-start priors
  reusing cortex/dp.py's mechanism verbatim; the goal-archetype
  marketplace with the action whitelist, closed schema, consent and
  capability discipline, review-only imports.
- H uncertainty hardening (3b07d07): every touched module named in
  the CHANGELOG line — duration posterior bands, health labels,
  dual-number unit conversion, Holt band + Kalman interval, stats
  describe() audited (already carried sem).
- Phase 2 (560789e): adversarial verification and cross-references.

Honest findings (the ones a human should read before trusting):

- Group G gating left deliberately UNDECIDED (OPEN_QUESTIONS in
  archetype_pack.py): what promotion from review-only to registered
  looks like — committed file vs interactive flow vs a typed CLI verb
  — is a human call; import implements none of it. The graph audit
  is reported but NOT an import gate (the current default may be too
  soft; not my call to make).
- The tempting per-source logistic for stacked fusion weights is
  CIRCULAR (the label is true exactly when the edge is positive, for
  any source including a random one) — the shipped weight is the
  non-circular chance-lift statistic, with the circularity documented
  in the module docstring.
- The cold-start hostile-artifact finding from the adversarial sweep:
  an unbounded imported prior could permanently silence an arm;
  fixed with a 1000-pseudo-observation ceiling, clipped and reported.
- The CRF-vs-perceptron calibration comparison (Brier 0.094 vs 0.219
  on the build fixture) is ONE synthetic corpus's result; it may flip
  as real supervised history grows — both taggers stay selectable.
- The adaptive RK45's one-knob mixed tolerance bounds ABSOLUTE error:
  solutions decaying tens of orders of magnitude (e.g. y' = -1000y)
  are resolved only to ~tol*span; a two-knob rtol/atol controller is
  the known fix, left as a documented envelope.
- Topic-drift per-snapshot NMF bases would compare incompatible topic
  spaces (the tests caught this mid-build); the shipped version builds
  ONE basis over the union corpus and projects each snapshot onto it.
- Merkle recursion depth is Python's recursion limit (~1000 nested
  directories) — loud RecursionError, not a silent wrong answer; a
  cap was deliberately not invented.
- gen_adapter byte-identity in Group B's commit message was recorded
  as run-after-the-fact rather than claimed preemptively (the first
  full-suite run also caught the AST import lint firing on a stray
  `shutil` in my own test file — fixed; the lint works).

De-redundancy: the duplication check found genius/graphs.py already
shipped articulation_points (Group E deepened the archetype instead
of duplicating); sysintel's batch "Drain-style" miner and the new
streaming drain.py are documented as different mechanisms, not
merged; LICENSING_OPEN_QUESTION and PR_SURFACE_PLAN re-read, verdicts
untouched, one paragraph added to the latter for Group G's new
standalone-only surface.

Final verification (this session, in order): unittest 2165 passed /
12 skipped OK (baseline 1987, +178); selfcheck OK; gen_adapter
--verify byte-identical against a fresh shallow clone of the upstream
checkout; bash test_assistant.sh 10/0; the deliberate AST-lint
negative probe fired on socket/subprocess/os.system and the tree
verified clean after deletion.
