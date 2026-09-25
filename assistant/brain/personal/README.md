# assistant/brain/personal — opt-in personal tools (NOT issue #120)

**Separation statement.** This package is *not* part of the
[caelestia-kde issue #120](https://github.com/ladybug-me/caelestia-kde) feature
surface and is not proposed for inclusion in the shell. It contains the
personal-knowledge-management engines that historically lived flat in
`assistant/brain/` before the scope split: they read a markdown vault and a
private state file, and have **zero** interaction with `shell.json`, the
settings layer, the JSON bridge, or any `caelestia-assist` subcommand.

## What lives here

| Module | Algorithm | What it answers |
| --- | --- | --- |
| `vault.py` | front-matter/inline-tag parser | "what's in my notes" |
| `graph.py` | PageRank, label-propagation communities | "which notes matter, what clusters" |
| `srs.py` | FSRS-*inspired* spaced repetition | "what's due today" |
| `survival.py` | Kaplan-Meier estimator | "will this task ever finish" |
| `journal.py` | Brier score + calibration curve | "how good are my confidence calls" |
| `ghost.py` | action-phrase vs known-task overlap | "which tasks am I ghosting" |
| `linkrec.py` | Adamic-Adar + shingle-Jaccard fallback | "which notes should link" |
| `health.py` | stale/orphan/duplicate composite 0–100 | "which notes need attention" |
| `planner.py` | 0/1 knapsack + Critical Path Method | "what fits in my day" |
| `duration.py` | Bayesian log-normal duration model | "how long does this category take" |
| `priority.py` | logistic priority fit from ledger labels | "what matters first" |

Shared engines that stayed in `assistant/brain/` root (imported via
`..`): `nlp.py` (tokenizer), `minhash.py` (MinHash/LSH),
`naive_bayes.py`, `textmine.py` (TF-IDF/TextRank), `spellfix.py`
(SymSpell-style), `bandit.py` (Thompson hour arms), `state.py`, `ledger.py`.

## Entry point

```bash
python3 -m assistant.brain.personal --help
python3 -m assistant.brain.personal organize ~/vault
python3 -m assistant.brain.personal plan tasks.json --minutes 240 --propose
```

The shell-side brain CLI (`python3 -m assistant.brain`) deliberately exposes
none of these subcommands, and the JSON bridge (`caelestia-assist api`)
exposes none of these operations. The only root→personal import in the
codebase is `dreamtime.py` reusing the `planner.knapsack` engine for the
assistant's *own* batch-window scheduling — an engine import, not a
personal-surface dependency.

## Honesty notes

- Everything here is proposal-only: the same `ledger.py` propose/approve
  discipline as the shell side, so nothing is ever modified without a
  decision recorded first.
- The SRS is FSRS-*inspired* (same retrievability shape, simplified
  stability dynamics), not the published FSRS weights.
- Cold-start priors are deliberately weak: with no data the tagger and the
  priority model refuse to rank rather than guessing.
