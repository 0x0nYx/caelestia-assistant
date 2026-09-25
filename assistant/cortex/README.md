# The Cortex Layer — learned intelligence, no LLM

The cortex package is the assistant's **learned routing and reasoning layer**:
it takes any natural-language request and decides what the assistant should do
about it — using classical, auditable machine learning instead of a language
model. It is the intelligence half of issue #120's architecture; the existing
deterministic spine (planner validation, single-writer applier, ledger
approve/reject) remains the safety half, unchanged.

```
user phrase
   │
   ▼
session.py          anaphora / ellipsis / clarification answers
   │
   ▼
compound.py         "disable blur and move the dock left" -> clauses
   │
   ▼
router.py           rank ALL 277 tools + presets + coarse surfaces
   │                 (BM25+ lexical, PPMI semantic, char-ngram fuzzy,
   │                  frozen-noun grammar, pattern floors, cue-kind
   │                  agreement, name-atom coverage)
   ▼
pipeline.py         cues -> ops -> settings.planner (validation, ranges)
   │
   ▼
{ PLAN, QUESTION, ABSTAIN, EXPLAIN, UNDO, LIST, INERT, DELEGATE }
   │
   ▼  (only ever via the existing gates)
chat y/N ──► applier.apply ──► history/undo ──► learn.py observes the outcome
```

## Why this beats a frozen grammar (and where it deliberately doesn't)

The frozen grammar of `settings/parser.py` covers 18 hand-verified tools and
honestly refuses everything else. The cortex extends addressability to all
277 registry tools plus presets, explain, undo, history, and the other layers
(diagnose / search / brain / issue) — mechanically:

- every tool's **name atoms** (`setGreeterMorningStart` → "greeter morning
  start"), path segments, group, enum values, and (for the core 18) its frozen
  nouns become addressable vocabulary;
- a seeded **domain lexicon** maps user words onto registry vocabulary
  ("see-through" → transparency, "gaps" → spacing);
- **typo correction** (unique edit-distance-1 matches only) and **stemming**
  make the match robust;
- two **deterministic structural layers** (pattern floors and cue-kind
  agreement) keep grammar beating statistics, so a why-question can never
  lose to a coincidental noun overlap.

The router **agrees with the frozen parser top-1 on every phrase the parser
can parse** (pinned by `RouterParserAgreementTests`); it only adds coverage
where the parser says NO_INTENT.

## The algorithms (every one real, named, and stdlib-only)

| Where | Algorithm |
|---|---|
| `lexicon.stem` | domain-reduced Porter suffix stripping (idempotent rule set) |
| `lexicon.levenshtein` | two-row DP edit distance with bounded early exit |
| `lexicon.jaro_winkler` | Jaro similarity + Winkler prefix boost |
| `lexicon.ngram_similarity` | character 3-gram cosine (compound-name matching) |
| `vectorize.TfidfIndex` | Okapi **BM25+** (delta lower-bound, k1/b tuned) |
| `vectorize.PpmiEmbedder` | **PPMI** co-occurrence matrix + **Achlioptas sparse random projection** (Johnson–Lindenstrauss), sublinear-tf text embedding — the "poor man's word2vec" |
| `router` | hybrid scoring + softmax-with-temperature + margin-based honest verdicts |
| `router` typo fix | unique-candidate bounded Levenshtein correction |
| `compound` | conjunction/contrast clause segmentation with content guards |
| `session` | anaphora/ellipsis resolution + ordinal/yes/no answer grammar |
| `nlhistory` | number-words/time-window grammar + recency/scope resolution |
| `memory` | Ebbinghaus-style exponential decay recall, market-basket **lift** co-change analysis, hour/weekday habit histograms |
| `learn.OnlineLogistic` | **AdaGrad** online logistic regression over router features |
| `learn.Calibration` | Beta-Binomial posterior acceptance per confidence bucket |
| `learn.CortexLearner` | **Thompson sampling** bandit over routing strategies (reuses brain's NamedBandit), acceptance-rate drift report |
| `corpus` | deterministic paraphrase generation — self-supervised training data with no LLM |

## The self-learning loop

Every routed request whose outcome the assistant can observe feeds three
learners (persisted in the brain's `state.json`, same atomic-write path as
every other learned model):

1. **the router weights** — accepted routes reinforce the signals that found
   them; rejected routes damp them (online logistic regression);
2. **the strategy bandit** — lexical-heavy / semantic-heavy / balanced weight
   profiles compete per query; outcomes reward arms;
3. **the calibration** — Beta-Binomial posteriors per softmax-confidence
   bucket; the pipeline reports the *calibrated* probability, not the raw
   softmax.

The **episodic memory** records every interaction with a forgetting curve,
computes co-change lift, and powers the proactive follow-up ("you usually
also tighten spacing when you shrink the bar"), which surfaces as a ledger
proposal — never an auto-apply.

## Commands

```
caelestia-assist chat                      # conversational REPL (y/N gated applies)
caelestia-assist route "make my bar thinner"   # one-shot, read-only, --json
caelestia-assist cortex report             # learning + memory dashboard
caelestia-assist cortex recall "bar"       # episodic recall
caelestia-assist cortex reset-learning     # weights back to priors
caelestia-assist cortex suggest setBarScale [--apply]   # co-change follow-up
```

JSON bridge ops (for the shell / scripts):

```
{"op": "route", "text": "...", "file": "..."}
{"op": "chat_turn", "text": "...", "session": {...}}       # session round-trips
{"op": "cortex_report"}
{"op": "memory_recall", "query": "...", "k": 10}
{"op": "learn_feedback", "text": "...", "surface": "...", "features": {...},
 "p": 0.6, "outcome": "applied", "strategy": "balanced"}
```

## Safety posture (inherited, not reinvented)

- **Nothing writes from the cortex.** Routing, ranking, planning — all
  read-only. The only write paths remain `settings.applier.apply` (behind
  `--apply` / the chat y/N gate) and the ledger-approved brain bridge.
- **Honest verdicts everywhere.** AMBIGUOUS asks a question with candidates;
  ABSTAIN says no match; NOT_FOUND for scoped undo refuses to fall back to
  undo-the-latest; out-of-range values stay planner-REJECTED, never clamped.
- **Determinism where it matters.** The router is a pure function of
  (text, state); the embedder's random projection is fixed-seed; the strategy
  bandit's RNG is seeded. Learned state changes only through observed
  outcomes.
- **Evidence for every route.** Matched terms, synonym and typo fixes, noun
  hits, pattern hits, and coverage — shown to the user next to the plan.
- **stdlib-only**, enforced by the same ALLOWED_IMPORTS AST scan as the rest
  of the assistant (`caelestia-assist selfcheck`).

## Tests

`python3 -m unittest discover -s assistant/cortex/tests` — 103 tests covering
every module, the router↔parser agreement regression, end-to-end pipeline
plans against temp files, apply/undo round-trips, learning convergence,
persistence round-trips, and the y/N consent gate.
