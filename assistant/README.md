# caelestia-assistant — on-device troubleshooting helper

A narrow, offline-first assistant for caelestia-kde. It helps with
easy-to-intermediate Linux shell and KDE/Quickshell troubleshooting, folder
organization and cleanup, and drafting (never submitting) issue reports for
this repository — plus, as its own separate module, a natural-language
settings editor for the shell's `shell.json` (issue #120) with read-only
explainability, bounded undo, and named presets — plus the **genius layer**
(`assistant/genius/`): a universal local intelligence layer that does any
kind of task (math, logic, probability, statistics, decisions, text
analysis, forecasting, system mining, goal decomposition) with classical
algorithms and no language model at all.

It is **not** a chatbot, **not** a general LLM feature, and nothing was
trained for this. Everything runs locally from this repository using only
the Python 3 standard library.

## What it does (and does not do)

| It does | It never does |
| --- | --- |
| Match your pasted errors against known signatures from this repo's docs and resolved issues, and print a fix plan | Execute any command, ever — not now, not with a flag, not ever |
| When nothing matches, find the closest *real* past resolution from the repo's own docs and issue history | Send anything anywhere (the only network surface, off by default, is a localhost Ollama you choose to enable) |
| Optionally, if you run a local Ollama server and explicitly ask for it, draft a *suggestion* for genuinely novel problems, grounded in retrieved context | Edit `shell.json` except through the settings layer's explicitly-requested `--apply` (dry-run by default, multi-change plans gated behind `--confirm`, backup written first, one-level `--restore` plus a bounded 12-entry `--undo` history) — it never deletes anything, never touches any other file, and never executes a command to change settings; scheme/wallpaper requests stay inert suggestions |
| Compose a clean, paste-ready issue draft from a described problem — into a local file only | Post, submit, open, or file anything, anywhere |

Every suggested command is printed as an inert string prefixed
`SUGGESTED_NOT_EXECUTED:` — with a risk label (`READ_ONLY` <
`STATE_CHANGING` < `PRIVILEGED` < `DESTRUCTIVE`) in the troubleshooting
layers; the settings layer's scheme/wallpaper suggestions carry the same
inert prefix. You read it, you decide, you copy-paste it yourself.
Destructive suggestions produced by the generative layer are withheld
outright.

## Using it

From the repository root (or after installing, from `assistant/bin/`):

```bash
# Layer 1 + 2: diagnose pasted text/logs (text argument or stdin)
python3 -m assistant.pipeline "vesktop freezes when I screenshare"
cat /tmp/caelestia_build.log | python3 -m assistant.pipeline

# Layer 1 only, with JSON output
python3 -m assistant.diagnostics.cli diagnose journal.log --json

# Validate rules + the no-executor import policy
python3 -m assistant.diagnostics.cli selfcheck

# Layer 2 only: search the repo's own corpus
python3 -m assistant.retrieval.cli search "workspace pills not loading" -k 3

# Layer 3 (OFF by default): generative suggestion via your local Ollama
python3 -m assistant.generative "weird flicker nobody documented" --generative

# Layer 4: draft an issue report (preview first; --confirm writes a local file)
echo "bar widgets disappear after every update" | \
  python3 -m assistant.issues.cli draft --title "Bar widgets disappear after update"
python3 -m assistant.issues.cli list-similar --from-file problem.txt
```

Optional environment variables (Layer 3 only):
`CAELESTIA_ASSISTANT_OLLAMA_URL` (must be loopback; default
`http://127.0.0.1:11434`) and `CAELESTIA_ASSISTANT_OLLAMA_MODEL`
(default `llama3`, matching `aiconfig.hpp`).

**Model guidance.** Which model to serve locally for the optional Layer 3
— and why the answer is "a small open-weight instruct-class model at the
8B scale, quantized, e.g. the Apertus 8B family" — is documented in
`assistant/generative/MODELS.md`. Guidance only: the layer's code and its
`llama3` default are unchanged, and nothing is ever trained or downloaded
by the assistant.

## Settings editing (the #120 feature)

A fifth, separate module (`assistant.settings`) — not one of the four
troubleshooting layers — turns a natural-language request into validated
tool calls on the shell's `shell.json`, and writes only behind an explicit
`--apply`:

```bash
# dry-run plan (the default; this run writes nothing)
python3 -m assistant.settings "Make my bar thinner."

# the write gate: apply the plan (backup written first)
python3 -m assistant.settings "Make my bar thinner." --apply

# the full tool registry, grouped by feature area (19 groups)
python3 -m assistant.settings --list-tools
python3 -m assistant.settings --list-tools --group effects
python3 -m assistant.settings --tool setBarScale   # one tool: range + citations

# direct tool calls (repeatable; values are JSON / bare enum tokens)
python3 -m assistant.settings --call setBarScale=1.2 --call setDockIconSize=40

# read-only: why does it look like this? (never writes)
python3 -m assistant.settings --explain "why is my dock blurry"

# bounded undo history (12 applies, oldest evicted)
python3 -m assistant.settings --history
python3 -m assistant.settings --undo 2
python3 -m assistant.settings --undo-id 7

# named presets: bundles of validated tool calls (multi-change -> preview + confirm)
python3 -m assistant.settings --list-presets
python3 -m assistant.settings --preset minimal --apply --confirm

# one-level undo of the very last apply (consumes the backup slot)
python3 -m assistant.settings --restore

# scheme-system requests stay inert suggestions
python3 -m assistant.settings "make my accent color blue"
```

`--file PATH` targets another `shell.json` (the tests use it); `--json`
emits the machine-readable plan. Absolute out-of-range values are rejected
(apply refused, exit 1, nothing written); relative asks are clamped with a
visible notice. Any plan touching more than one setting prints the
preview ("I found several changes that match your request:" + per-change
`path: old -> new` lines + "Apply these changes?") and is written only
behind `--confirm` (or an interactive yes); single-setting applies stay
direct, exactly as issue #120 frames the confirmation step.

Mapping honesty: this port has `bar.scale`, not pixel bar height, so
"thinner" maps to `bar.scale`; there is no dock left/right key — "move the
dock to the left" answers AMBIGUOUS (dock placement is a `bar.entries`
zone; it offers to move the whole bar instead); accent color and wallpaper
live in the scheme system, so those requests are suggested, never applied.

The natural-language grammar covers a frozen surface of 18 everyday tools
(bar scale/position, dock icon size and badges, blur, appearance scaling,
border thickness, launcher size, bezel mode, notification counts) — each
grounded in the shipped Nexus UI and addressable by plain words. The full
registry underneath is generated straight from the shell's own C++ config
headers plus a transcription of every shipped Nexus control: **277 tools in
19 feature-area groups**, every tool double-cited (C++ declaration line +
shipped control), with the leaves that are deliberately not exposed
(credentials, endpoints, the master switch, kwinrc companions, no shipped
control, ...) recorded each with its reason. The other 259 tools beyond the
frozen 18 are addressed by name (`--call`/`--tool`/`--group`), not by plain
words — see `assistant/settings/DESIGN.md` for the full design record,
including which tools were evaluated and left out, and why.

The registry also powers a native QML service
(`shell/services/SettingsTools.qml`) wired into the sidebar AI assistant
(`shell/modules/sidebar/AiAssistant.qml`) as 8 settings meta-tools with
preview-then-confirm cards, so the in-shell assistant can call the same
validated tool surface in-process, with no Python dependency at shell
runtime.

## The cortex layer — learned routing for every request (no LLM)

The frozen 18-tool grammar above answers everyday phrasings and honestly
refuses the rest. The cortex layer (`assistant/cortex/`) extends the SAME
safety spine to every request, with classical machine learning instead of
a language model:

```bash
# one-shot: any phrase -> ranked surfaces + validated plan (read-only)
python3 -m assistant.cortex.cli route "push the greeter morning start later"

# conversational REPL: context, clarifying questions, y/N-gated applies
python3 -m assistant.cortex.cli chat

# the learning + memory dashboard (calibration, strategies, drift, habits)
python3 -m assistant.cortex.cli cortex report
```

What it adds over the frozen grammar:

- **All 277 tools become word-addressable** through their name atoms,
  paths, groups, enum values and the seeded synonym lexicon — with typo
  tolerance ("transparncy" still routes) and stemming.
- **Compound requests split and compose**: "disable blur and move the dock
  left" plans two validated ops; "but keep the blur on" is honored as
  do-not-touch.
- **A conversation with context**: "a bit smaller now" resolves against
  the setting you just discussed; ambiguous routes ask a question and
  understand ordinal/yes/no answers.
- **Natural-language undo/history**: "undo the last change", "undo the bar
  changes", "restore yesterday's theme" — scoped, honest (no matching
  entry -> nothing undone, never a silent fallback).
- **Calibrated confidence and evidence** on every route: matched terms,
  synonym/typo fixes, grammar hits — the plan card shows why.
- **Self-learning from your decisions**: accepted/rejected routes fit the
  router weights (online logistic regression), a Thompson-sampling bandit
  picks the signal mix, Beta-Binomial calibration keeps the confidence
  honest, and an episodic memory with a forgetting curve powers co-change
  suggestions ("you usually also tighten spacing when you shrink the bar")
  as ledger proposals — never auto-applied.

The router is pinned by tests to agree with the frozen parser top-1 on
every phrase the parser can parse; it only adds coverage where the parser
says NO_INTENT. Nothing in the cortex writes anything: applies still go
through the chat y/N gate or `--apply`/`--confirm`, and the planner still
rejects out-of-range values. See `assistant/cortex/README.md` for the
algorithm inventory (BM25+, PPMI + random projection, AdaGrad, Thompson
sampling, market-basket lift, ...) and the JSON bridge ops.

## The genius layer — a universal task engine (still no LLM)

`assistant/genius/` extends the same posture to every kind of request:

```bash
# the front door: classify any request, dispatch, show the evidence
caelestia-assist do "what is 15% of 80"
caelestia-assist do "solve x^2 - 2 = 0"
caelestia-assist do "is (p and q) -> (p or r) a tautology"
caelestia-assist do "how do i fix the flaky test"

# direct domain access
caelestia-assist genius stats "3, 9, 12, 1, 44"
caelestia-assist genius decide --matrix '[[8,256],[6,512]]' --labels air,pro \
    --criteria battery,storage --weights .5,.5 --method topsis
caelestia-assist genius history ~/.bash_history
```

What it adds (see `assistant/genius/README.md` for the full algorithm
inventory): a symbolic-lite math engine (parser, differentiation, root
finding, quadrature, RK4, Taylor series), matrix algebra, probability
(Bayes chains, Markov chains, Monte Carlo), a statistics engine with
real special functions and p-values, CSV/time-series analysis
(Yule-Walker AR, CUSUM changepoints, clustering), propositional logic
with a DPLL SAT solver and CSP search, Bayesian networks and HMMs
(Viterbi), decision analysis (AHP with consistency ratios, TOPSIS,
minimax, Pareto, EVPI), language intelligence (sentiment, six
readability formulas, RAKE/YAKE keywords, extractive QA, language
detection, a self-learning classifier), Markov generation and sequence
prediction, read-only system mining (shell history association rules,
duplicates by hash, Drain-style log templates, JSON linting), OKLab
color science (palettes, WCAG contrast), HTN goal decomposition, and a
metacognition module that induces rules from your own decisions and
chooses its next question by maximum information gain.

The router learns from your feedback (`genius learn` / the
`genius_learn` bridge op) and the cortex delegates to it: a
non-settings question in `caelestia-assist chat` is answered by the
genius layer inline, read-only, with its evidence.

## How it decides things

1. **Layer 1 — deterministic rules (no ML).** Your text plus any pasted logs
   are matched against signatures in `assistant/diagnostics/rules.d/`, drawn
   from `docs/TROUBLESHOOTING.md` and the resolved issue history (#6, #14,
   #333, #402, #418, #461, #528, #616, #641, #763 and others). Scoring is
   fixed-weight and fully reproducible. If several rules fit within the
   margin, it says AMBIGUOUS and asks a clarifying question instead of
   guessing. If nothing fits, it says so honestly and points at diagnostic
   commands.
2. **Layer 2 — local retrieval.** A BM25 index (built once by
   `python3 -m assistant.retrieval.build`, committed as JSON) over 39 corpus
   documents: the troubleshooting guide, the architecture docs, the README,
   and one document per reachable resolved issue, with resolutions quoted
   only from what maintainers actually wrote. Retrieval hits are labeled
   "closest past resolutions, NOT verified diagnoses".
3. **Layer 3 — optional generative suggestions.** Only for problems Layers 1
   and 2 cannot name. Retrieval excerpts are the only grounding context; the
   output passes through a sanitizer that labels every command and withholds
   destructive ones. The model is never contacted with zero retrieval hits,
   never contacted on a non-loopback host, and never contacted unless you
   pass `--generative`.
4. **Layer 4 — issue drafting.** Renders your description into the shape of
   this repo's real `.github/ISSUE_TEMPLATE/*.yml` templates, adds an
   environment block and a dedup advisory from Layer 2, and writes a local
   draft file (only with `--confirm`) that starts with
   `DRAFT — NOT SUBMITTED TO ANYWHERE`.
5. **Settings editing — deterministic intent parsing (separate module).**
   A natural-language settings request is parsed by a fixed regex grammar —
   no ML, no network — into validated tool calls against the 277-tool
   registry described above. The 18 everyday tools answer plain words; the
   rest are addressed by name through `--call`. AMBIGUOUS asks get a
   clarifying question, NO_INTENT lists the supported settings, `--explain`
   answers "why does it look like this" read-only, and the printed plan
   stays a dry-run until you pass `--apply` (multi-change plans additionally
   need `--confirm`).

## Where its limits are

- **It only knows this repository.** The corpus is the repo's docs plus
  reachable resolved issues. Anything outside that is, at best, a
  clearly-labeled retrieval guess or an optional local-model suggestion.
- **Layer 1 is literal.** Exact regex/substring signatures only — no fuzzy
  matching. If your wording differs from every known signature, it will
  answer "no known signature matched" rather than improvise.
- **Retrieval hits are not truth.** A close historical match may not be your
  bug. That is why every Layer 2 answer carries the not-verified banner.
- **The generative layer is a suggestion box.** A small local model reading
  excerpts can be wrong or outdated; its output is sanitized, but the
  safety of any command still depends on you reading it first.
- **Issue drafts are drafts.** They are not checked against the live
  tracker (offline by design); the dedup advisory is advisory.
- **Cleanup help is report-first.** Folder rules state
  `safe_to_delete: yes | ask_first | never` per target and the assistant
  deletes nothing itself.
- **Settings editing is global-file only, with bounded undo.** It edits the
  global `shell.json` — never per-monitor override files (it only warns when
  one would shadow a change) — and writes behind `--apply` (multi-change
  plans additionally behind `--confirm`). Undo is a bounded 12-entry history
  (`--undo`/`--undo-id`, oldest evicted) plus the single-slot `--restore`;
  redo is deliberately not offered. The named presets are conservative
  bundles of validated tool calls, not upstream-defined looks. The
  in-shell side (SettingsTools.qml) is statically guarded but was never
  compiled or run in the build environment — it needs a maintainer's
  review like everything else here.

## Safety model, in one paragraph

The assistant contains no code that can execute a program: the import
policy (enforced by an AST scan in CI and by the test suites) forbids
`subprocess`, `os.system`, `socket`, `urllib`, and friends across the whole
`assistant/` tree, and rules literally cannot express auto-execution
(forbidden keys are a lint error). The only network code in the tree is the
Layer 3 Ollama client, which is off by default, single-attempt, and
hard-rejects any non-loopback host before connecting. The only files the
assistant ever writes are Layer 4 draft files behind `--confirm` and, in
the settings layer, the target `shell.json` behind an explicit `--apply`
(plus its backup, transient tmp and bounded-history siblings — four paths,
all next to the target, for one-level `--restore` and bounded `--undo`).
Run `python3 -m assistant.diagnostics.cli selfcheck` to re-verify the core
invariants on your machine.

## Tests

```bash
python3 -m unittest discover -s assistant/diagnostics/tests   # deterministic-rule engine, incl. real-issue regressions
python3 -m unittest discover -s assistant/retrieval/tests     # offline retrieval, incl. golden queries
python3 -m unittest discover -s assistant/generative/tests    # optional generative layer, incl. bypass + model-guidance tests
python3 -m unittest discover -s assistant/issues/tests        # issue drafting, incl. gate tests
python3 -m unittest discover -s assistant/settings/tests      # settings layer, incl. #120's example sentences, registry drift guards, QML cross-checks
bash tests/run-tests.sh test_assistant.sh                     # repo-suite integration (all five suites; run from an upstream checkout)
```

## Relationship to the shell's AI sidebar

The shell already ships an AI assistant (`shell/modules/sidebar/AiAssistant.qml`,
configured via `aiconfig.hpp`) with provider integrations. The CLI layers
of this assistant remain independent of it on purpose: reviewable, offline,
standards-based. `shell/services/SettingsTools.qml` is the one deliberate,
separately-reviewable touchpoint between the two: a native QML singleton
that exposes the same generated 277-tool registry (embedded from
`assistant/settings/tools.json`, byte-checked by a Python test) to the
sidebar's agent loop as 8 settings meta-tools with preview-then-confirm
cards — property writes through `GlobalConfig`, no runtime Python. The QML
is statically guarded but was not compiled or run in the build
environment; it waits for human review like everything else in this tree.

A second touchpoint, same discipline: the sidebar's tool registry now
carries five `caelestia_genius_*` entries (math, stats, logic, decide,
palette) that dispatch through the assistant's JSON bridge
(`caelestia-assist api`, read-only ops only). The framing is exactly the
one the issue thread asks for: the shell's existing Ollama-backed
assistant can now call a deterministic tool instead of guessing — "what's
15% of 840" becomes `840*0.15` evaluated by the math engine, "which of
these two laptops" becomes a TOPSIS ranking with its full evidence, and a
proposed accent color gets a WCAG contrast check before any (still inert)
scheme suggestion. The model is never the calculator. The registry
entries' argument specs are pinned to the bridge ops' actual parameters
byte-for-byte by `assistant/brain/tests/test_ai_assistant_qml.py`, the
same drift-guard pattern the settings suite uses for tools.json ↔
SettingsTools.qml. These five tools were chosen from the priority list
discussed on issue #120 and ship in one reviewable round; nothing else
(sysintel, filesystem scanning, history mining) is exposed.

## One entry point: `caelestia-assist`

Every module is reachable through one router (`assistant/hub.py`, also
`python3 -m assistant`):

| Command | Routes to | Writes anything? |
| --- | --- | --- |
| `diagnose FILE`, `selfcheck` | Layer 1 rules | No |
| `ask "text" [--generative]` | Layers 1 to 3 pipeline | No (Layer 3 is opt-in, loopback) |
| `search "query" [-k N]` | Layer 2 retrieval | No |
| `issue draft \| list-similar ...` | Layer 4 issue drafting | Only with `--confirm` |
| `settings "request" [--apply]` | Natural-language `shell.json` editing | Only with `--apply` |
| `brain <command> ...` | Lean intelligence layer (`assistant/brain/`) | Ledger and state files only |
| `api < request.json` | JSON bridge for the brain | Same as `brain` |

The JSON bridge is the interface for the shell: one request object on stdin,
one response object on stdout, exit code 0 on success. Example:

```bash
echo '{"op": "plan", "tasks": [{"id": "a", "effort_min": 45, "importance": 0.9}], "minutes": 120}' \
  | caelestia-assist api
```

Brain operations only ever create proposals in a ledger; nothing is applied
until the user approves it through `ledger_decide`.

### Settings changes now go through the same ledger

`assistant/brain/settings_bridge.py` wires the settings layer (above) into
the brain's proposal ledger, so a preset or tool-call change is a durable,
inspectable proposal — not just a one-shot `--confirm` prompt — using the
exact same approve/reject pattern the brain already uses for tag and
dedup suggestions:

```bash
# propose (dry-run only; nothing is written yet)
caelestia-assist brain settings propose ~/.config/caelestia/shell.json --preset compact

# approving IS the #120 confirmation step: only now does the real,
# already-safety-reviewed applier write (backup + bounded history, as always)
caelestia-assist brain settings decide 1 approve
caelestia-assist brain settings decide 2 reject   # writes nothing

# which presets does this user actually keep? (Thompson sampling over
# approve/reject history, per preset — never auto-applied)
caelestia-assist brain settings recommend
```

No new write path is introduced: `settings_bridge` only calls the existing
`settings.planner` (read-only plan) and `settings.applier` (the sole
writer, and only with `write=True`, which happens exactly once — on
ledger approval). A settings proposal tagged with a preset name also
rewards `brain/preset_bandit.py` (a named-arm generalisation of the
hour-of-day `HourBandit`), so `recommend` naturally favours presets this
user tends to approve without ever changing what a preset validates to.

Two more calibration/learning touches, both additive to the above:

- **Confidence is self-calibrating.** A proposal's stored `confidence`
  defaults to this ledger's own historical approval rate for
  `kind="settings"` (via `brain/calibrate.py::acceptance_rate`, the same
  Beta-Binomial bookkeeping already used to decide how hard to push other
  proposal kinds), not a fixed optimistic number — a user who keeps
  rejecting settings changes sees that reflected honestly next time.
- **Learning isn't preset-only.** Every proposal, preset or raw `--call`,
  also rewards the bandit once per distinct tool it touched (under a
  `tool:` arm prefix), so `brain settings recommend --tools` can rank
  individual settings by acceptance even when they were never bundled in
  a named preset.
