# caelestia-assistant

**An offline-first, on-device intelligence layer for [caelestia-kde](https://github.com/ladybug-me/caelestia-kde) — and a working answer to a harder question: how much of what we ask a frontier LLM can be answered by classical algorithms, deterministic pipelines, and careful engineering, at zero model cost, on a low-end machine?**

No language model in the critical path. No training. No network. Everything runs locally from this repository using only the Python 3 standard library, and every suggestion is something you approve.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-751%20passing-brightgreen)
![LLM required](https://img.shields.io/badge/LLM%20required-none-success)

---

## What it is

A shell-side assistant organized as **ten cooperating layers**, each replaceable, each honestly scoped:

| Layer | Package | What it answers | Core machinery |
| --- | --- | --- | --- |
| Diagnostics | `assistant/diagnostics/` | "Which known problem is this?" | Deterministic rule engine over signature→fix mappings, every rule citing its source |
| Retrieval | `assistant/retrieval/` | "What is the closest *real* past resolution?" | BM25 over the repo's own docs and resolved issues |
| Generative *(optional)* | `assistant/generative/` | Novel problems, only if you ask | Loopback-only local Ollama, sanitized output, off by default |
| Issue drafting | `assistant/issues/` | "Draft this bug report" | Structured templates → local file, never submitted |
| Brain | `assistant/brain/` | Proposals, preferences, time, habits, files | Shell-native intelligence: ledger + settings bridge (#120), rhythm/forecast/anomaly engines, prefs, tidy, brief — with the personal-PKM tools split out into an opt-in subpackage |
| Cortex | `assistant/cortex/` | Routing that *learns* your preferences | BM25+PPMI+char-ngram over 277 tools, AdaGrad online logistic, Thompson-sampling strategies, Beta calibration, episodic memory |
| Settings *(issue #120)* | `assistant/settings/` | "Make my bar thinner" → validated plan | 277-tool cited registry, planner validation, gated applier, bounded undo, presets |
| Genius | `assistant/genius/` | Math, stats, logic, decisions, data, text, system | 18-domain meta-router over stdlib engines |
| Scan | `assistant/scan/` | "Scan this 2 GB journal on a 4 GB laptop" | Aho-Corasick + Bloom + Count-Min + HyperLogLog + reservoir + Page-Hinkley, one pass, bounded RAM |
| Agent | `assistant/agent/` | "Clean my downloads, then make the shell minimal" | HTN goal decomposition → DAG → simulate → per-node consent → observe & learn |

### The brain layer (a partial inventory)

Multinomial Naive Bayes · MinHash+LSH near-duplicate detection · PageRank / label-propagation link graphs · Adamic-Adar link recommendation · logistic priority scoring · Bayesian log-normal duration estimates · 0/1 knapsack day-planning + Critical Path Method · Kaplan-Meier "this task will never finish" survival analysis · Holt trend + Kalman smoothing forecasts · FSRS-inspired spaced repetition · Thompson-sampling reminder bandits · z-score/entropy anomaly flags · SymSpell typo correction · TF-IDF + TextRank summarization · Brier-score confidence calibration · Beta-Binomial preference posteriors with exact credible intervals · journaled filesystem organization (crc32 dedup, collision-safe moves, rollback) · a deterministic daily brief.

**Scope split:** the personal-knowledge-management engines in that list (vault
organization, wiki-link graphs, spaced repetition, task survival, decision
journal, day planning, duration/priority models) live in
[`assistant/brain/personal/`](assistant/brain/personal/README.md) behind their
own entry point (`python3 -m assistant.brain.personal`). They read your notes,
not your shell config, and are **not** part of the caelestia-kde issue #120
feature surface. The brain root keeps only shell-native machinery: the
proposal ledger, the settings bridge (#120), preference/calibration models,
rhythm/forecast/anomaly engines, the filesystem organizer, and the brief.
The two halves share the generic utility libraries (`nlp.py`, `minhash.py`,
`naive_bayes.py`, `textmine.py`, `spellfix.py`) and nothing else.

### The settings layer — issue #120's contract

Natural-language → **Intent Parser → Structured Tool Calls → validated application**. Every one of the 277 tools carries its C++ declaration citation, its shipped Nexus control, and its live QML reader. Out-of-range values are **rejected, never clamped**. Multi-change plans get preview-then-confirm. A bounded 12-entry undo history is kept. The assistant never edits `shell.json` except through the explicitly-requested `--apply` gate with a backup written first. The same registry powers the in-shell QML service (`shell/services/SettingsTools.qml`), asserted byte-identical against `tools.json` by a unittest.

Issue #120 Phase 3 ("optimization profiles") ships as `assistant/settings/optimize.py`: five scored objective profiles (gaming / battery / minimal / comfort / accessibility), Pareto-frontier trade-off analysis across profiles, simulated-annealing and coordinate-descent preset synthesis, and AC-3 constraint propagation that refuses contradictory requests with reasons instead of half-applying them.

## The agent

```bash
$ caelestia-assist agent "vesktop freezes and crashes every time" --simulate
simulation (nothing executed):
  n1   scan_stream      execute scan_stream (read-only)
  n2   diagnose         execute diagnose (read-only)
  n3   retrieve_similar execute retrieve_similar (read-only)
  n4   fix_plan         execute fix_plan (read-only)
critical path: n1 -> n2 -> n4
```

The agent decomposes a request into a dependency-ordered task graph over all layers, **projects** it before touching anything, executes read-only nodes, and routes every state-changing node through an explicit per-node `y/N` consent. Refused nodes skip their dependents — nothing is ever half-applied. When the goal split is ambiguous, `--questions` asks the single question with the highest expected information gain (20-questions-style entropy reduction over hypotheses — a real dialogue skill with no language model inside).

Every outcome feeds the learners: an AdaGrad online-logistic over routing features, a Thompson-sampling strategy bandit, Beta-Binomial confidence calibration, split-conformal verdicts ("routes this confident were right ≥90% of the time historically"), query-by-committee active learning, and Page-Hinkley drift detection over your acceptance stream ("your preferences shifted this week").

## The safety contract

Enforced in code, not policy — by an AST lint (`assistant/diagnostics/schema_lint.py`) over every file in the tree, pinned by tests:

- **Never executes anything.** Suggested commands are inert strings prefixed `SUGGESTED_NOT_EXECUTED:` with a risk tier (`READ_ONLY < STATE_CHANGING < PRIVILEGED < DESTRUCTIVE`). Destructive suggestions are withheld outright.
- **No network** except an explicitly enabled, loopback-only, single-attempt local Ollama call in the optional generative layer. Non-loopback hosts are rejected before connecting.
- **No executor imports** (`subprocess`, `socket`, `shutil`, `ctypes`, … are rejected by name), no `os.system`/`os.popen` attribute calls, no auto-exec rule keys.
- **Write paths are enumerated**: `settings/applier.py` (behind `--apply`/consent, backup first, bounded undo), the brain's proposal ledger (approve/reject only), the agent's journaled tidy moves (rollback-able), and learned-state JSON files. Nothing else writes.
- **Honest verdicts everywhere**: `AMBIGUOUS` asks, `ABSTAIN` refuses, `NOT_FOUND` undo refuses to guess, out-of-range is rejected not clamped, thin evidence is labeled thin.

## Install & use

Requirements: Python 3.10+ (stdlib only — zero pip dependencies).

```bash
git clone https://github.com/0x0nYx/caelestia-assistant.git
cd caelestia-assistant
./assistant/bin/caelestia-assist --help          # or: python3 -m assistant.hub
```

```bash
# Troubleshoot pasted logs (rules first, then grounded retrieval)
caelestia-assist ask "vesktop freezes when I screenshare"

# Scan a huge journal in one pass with bounded memory
caelestia-assist scan ~/.local/state/caelestia-shell.log

# Natural-language settings (issue #120) — dry-run by default
caelestia-assist settings "make my bar thinner"
caelestia-assist settings "make everything minimal" --apply

# Optimization profiles (issue #120 phase 3)
caelestia-assist genius optimize pareto --help

# Setup wizard (issue #120 phase 3): AHP+TOPSIS over the shipped presets
caelestia-assist settings --wizard --answers 2,3,2,3,3,2

# Config health lint + wallpaper palette (inert suggestions only)
caelestia-assist settings --lint
caelestia-assist settings --wallpaper-palette ~/Pictures/wall.png

# One-shot telemetry snapshot (read-only /proc + /sys file reads)
python3 -m assistant.diagnostics.telemetry

# Batch-review near-threshold phrases (logged, never silently learned)
caelestia-assist cortex review list

# The second brain
caelestia-assist brief                       # today on one deterministic page
caelestia-assist brain tidy survey ~/Downloads
caelestia-assist brain prefs                 # what it believes about you

# Opt-in personal tools (NOT part of the #120 shell surface)
python3 -m assistant.brain.personal --help

# Any task, no chat needed
caelestia-assist do "solve x^2 - 2 = 0"
caelestia-assist do "summarize this: $(cat notes/foo.md)"
caelestia-assist genius graphs dijkstra '{"a":{"b":4,"c":1},"c":{"b":2},"b":{}}' --source a

# The agent
caelestia-assist agent "clean my downloads and then make the shell minimal" --simulate
caelestia-assist agent "clean my downloads"          # prompts y/N per gated node

# JSON bridge for the shell/scripts
echo '{"op": "agent_simulate", "text": "clean my downloads"}' | caelestia-assist api
```

Optional (Layer 3 only): `CAELESTIA_ASSISTANT_OLLAMA_URL` (loopback only; default `http://127.0.0.1:11434`) and `CAELESTIA_ASSISTANT_OLLAMA_MODEL` (default `llama3`, matching the shell's `aiconfig.hpp`). Model guidance lives in [`assistant/generative/MODELS.md`](assistant/generative/MODELS.md).

## Development

```bash
python3 -m unittest discover -s . -p "test_*.py"   # 751 tests, ~10 s
python3 -m assistant.hub selfcheck                 # rules + import-policy lint
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the import-policy contract and the discipline for adding tools to the settings registry. Design rationale (why rules-first, why BM25 over embeddings, why nothing is trained) lives in [`assistant/RATIONALE.md`](assistant/RATIONALE.md); the settings layer's full specification in [`assistant/settings/DESIGN.md`](assistant/settings/DESIGN.md).

## Honest limits

This is not a chatbot and does not try to be one. It cannot write an essay, reason about arbitrary novel prose, or see your screen. What it does — diagnose against a cited corpus, edit a configuration safely, mine a log at bounded memory, plan a day, organize files, compute, and learn your approval patterns — it does deterministically, offline, auditably, and on hardware that would struggle to load an 8B model. That trade is the point.

## License

Copyright © 2026 0x0nYx

This program is free software: you can redistribute it and/or modify it under the terms of the **GNU Affero General Public License** as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version — see [LICENSE](LICENSE).

This license was chosen deliberately: the assistant is a community project built around a strict no-execution safety contract, and AGPLv3 guarantees that anyone who improves it — including someone running a modified version as a network service — owes those improvements back to the community. Source disclosure is the price of distribution; nothing here executes behind a closed door, and the license keeps it that way.

If you fork it, keep it open. If you improve it, upstream it.
