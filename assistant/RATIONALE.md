# RATIONALE — design choices and why they were made

Scope source: the maintainer's direction in issues #120 and #802 — a narrow,
on-device assistant for easy-to-intermediate Linux shell / KDE / Quickshell
troubleshooting, folder organization and cleanup, and issue-report drafting;
never a general LLM, and (answering #802 directly) **nothing trained from
scratch**, because this repository does not hold nearly enough data for
training to produce anything but overfit. Approved scope also required that
issue reports are drafted only — never auto-submitted — and that a mistake
shipped to this repository costs trust that took a long time to build.

The choices below follow from that scope, and each is a fixed building
block the rest of the design assumes.

## 1. Deterministic rules first, no ML in the default path

The single most useful and safest artifact for this repo is a mapping from
known error signatures to known fixes — the same knowledge the maintainer
and contributors re-type in issue threads. `docs/TROUBLESHOOTING.md` and the
closed-issue history already encode it. A rule engine over that corpus is
auditable (every rule cites its source), reproducible byte-for-byte (same
input, same report), and testable against history (regression cases built
from real issue text). Ambiguity is surfaced, never hidden: when two rules
fit within the scoring margin the report says AMBIGUOUS and asks a
clarifying question, because a helper that picks silently will eventually be
confidently wrong.

## 2. Retrieval second — and grounded in the repo's own material only

When no rule matches, the honest next best is "the closest real past
resolution", not an invention. The corpus is strictly this repository's docs
plus reachable issues; resolutions quote only what maintainers verifiably
wrote (including capturing which PR actually closed an issue — e.g. #402 was
closed by PR #586, not the earlier attempt #408). Corpus growth is rule-based
and falsifiable: an issue enters only once it closed as completed, with its
resolution quoted verbatim from the maintainers' own comments — the corpus
frontier is simply the most recently closed issue that has entered so far.
BM25 over a committed JSON index was chosen over embeddings because it is
stdlib-only, fully offline, deterministic, debuggable (you can see which
token matched), and entirely adequate for a corpus this size. Runtime never
parses the corpus — it reads the index, keeping the import surface tiny.

## 3. Generative last, optional, loopback-only, sanitized — and nothing trained

Issue #802 asked about training a small model. The right adaptation is
retrieval-augmented generation over an existing small open-weight local
model via the Ollama stack the shell already ships (`aiconfig.hpp` defaults
to `llama3` on `localhost:11434`), used only for genuinely novel problems.
Constraints in code, not policy: off by default (`--generative`), one
attempt, short timeout, zero retrieval hits means the model is never
contacted, non-loopback hosts are rejected before any connection, and the
output passes a sanitizer that labels every command-shaped line
(`SUGGESTED_NOT_EXECUTED` + risk tier) and withholds DESTRUCTIVE ones
entirely. The layer degrades to plain retrieval whenever the server is
absent — no crash, no retry storm.

`assistant/generative/MODELS.md` adds model-choice guidance only: it points
at the Apertus 8B open-weight family — the family a maintainer collaborator
pointed issue #120 itself at — served quantized via the user's local Ollama,
with the honest note that the Ollama model library has no `apertus` listing
yet, so the recommendation is the family and the size class, not a command.
The layer's own default stays `llama3` (itself 8B-class, matching
`aiconfig.hpp`). Nothing is trained, nothing is bundled, and the mechanism
— loopback-only, off by default, single POST, sanitized — is unchanged by
that guidance.

## 4. Issue drafting stops at the draft

The drafting layer mirrors the repository's real templates
(`.github/ISSUE_TEMPLATE/*.yml`), adds an environment block the user would
otherwise be asked for (assembled from file reads only), and a dedup
advisory from Layer 2. It writes one local file behind `--confirm`, stamped
`DRAFT — NOT SUBMITTED TO ANYWHERE`. There is no network code in the module
at all, so "auto-file" is not a behavior that can be toggled — it does not
exist.

## 5. Structural safety over behavioral safety

Every guarantee is enforced by what the code *is*, not by what it promises:

- The engine has no executor: no `subprocess`, no `os.system`, anywhere in
  `assistant/` — enforced by an AST import scan with a single allow-list
  file (`ALLOWED_IMPORTS.txt`) whose changes are reviewable diffs. Suggested
  commands live in one inert string field, prefixed, risk-labeled, and
  schema-linted against the static classifier (under-declaring risk fails
  CI; over-declaring is allowed — the safe direction).
- Rules cannot express auto-execution: keys matching
  `auto_run/exec/execute/invoke/spawn/eval` are lint errors.
- The classifier's failure mode is conservatism: unknown commands default to
  `STATE_CHANGING`; recursive `rm` outside regenerable cache scopes is
  `DESTRUCTIVE`; anchors are hardened against prefix words, punctuation,
  backslash continuations, `-R`, case games, and ANSI escapes — each with a
  regression test from the adversarial review.
- An adversarial safety pass hunted auto-exec and auto-file paths, and the
  loopback guard is tested against dozens of smuggling probes
  (decimal/octal/hex IPs, userinfo, IPv6 zones, suffix hostnames).

## 6. Process choices

Layers are built bottom-up and frozen once green: Layer 1 passes its
historical regressions before Layer 2 exists; both pass before Layer 3
consumes them. Python stdlib-only was chosen over pip dependencies so the
assistant can run on a fresh Arch/Fedora/Debian install with nothing but
`python3`, and so the review surface is exactly the code in this repository.

## 7. The settings editor (issue #120): separate module, same posture

Issue #120 asks for natural-language *editing* of the shell configuration
— a different intent domain from the four troubleshooting layers, whose
cascade contract is problem → diagnosis → inert suggested fix. An edit
produces a *write*, so the feature lives in its own package
(`assistant/settings/`) with its own parser → planner → applier pipeline
rather than being folded into `rules.d`; that keeps both review surfaces
clean and the four layers' contract untouched.

Parsing is deterministic regex, not the local Ollama: a write path must be
reproducible, testable offline in CI, and byte-stable for review, and a
model in that path would contradict §3's no-training posture. The frozen
grammar covers #120's "simple NL requests" and degrades honestly —
AMBIGUOUS asks a clarifying question, NO_INTENT lists the supported
settings.

Writes target the watched global `~/.config/caelestia/shell.json` because
that file is the only external entry into the live config system (the
shell's IPC surface exposes no settings setter; `shell.qml` itself
registers only the `region` and `lock` handlers) — a plain, hot-reloaded
file write is as close to #120's "controlled API" as an external tool can
get, without building the in-shell ConfigManager/tool-calling API that
#120 sketches, which remains the maintainer's to design.

Dry-run by default with an explicit `--apply` is the CLI equivalent of
#120's confirmation step: the printed plan is the confirmation, the re-run
with `--apply` is the "yes", and shell history records it — auditable
after the fact, unlike an interactive prompt that behaves differently
under piped stdin.

Validation choices: an absolute out-of-range request is REJECTED (silently
rewriting "scale 9" to 1.6 would write something the user never asked for)
while a relative ask is CLAMPED with a visible notice (a direction, not a
target, was requested); undo is bounded (a 12-entry history plus a
single-slot `--restore` for the very last apply) rather than an unbounded
log, so the config directory doesn't accumulate timestamped snapshots; and
only the global file is written because per-monitor overrides are a
separate schema surface — warned about read-only, never touched.

The #120 tool names map honestly rather than literally: `setBarHeight` →
`bar.scale` (this port is scale-driven — `BarWrapper.qml:24` clamps
`Config.bar.scale`, and `barconfig.hpp` has no pixel-height key),
`setDockPosition` → `bar.position` plus an AMBIGUOUS dead-end (there is no
dock left/right key; dock placement is a `bar.entries` zone),
`setCornerRadius` → `appearance.rounding.scale` (rounding is token-scaled
— `appearanceconfig.cpp:32-33` multiplies the token by the scale — not
pixels), `setAccentColor`/`setWallpaper` → inert
`SUGGESTED_NOT_EXECUTED` strings (the scheme system, not shell.json), and
`toggleNotifications` → deliberately unmapped (no upstream on/off boolean
exists in `notifsconfig.hpp`).

The natural-language surface stays a frozen set of 18 everyday tools, each
grounded the same way (C++ declaration + shipped Nexus control + live QML
reader, ranges adopted from the shipped steppers); every other candidate
considered and left out — transparency on/off, drag thresholds, timeout
keys with a seconds-vs-milliseconds UI, enum compounds, anything
string/list/command-typed — is documented as not-a-tool with its specific
reason in `assistant/settings/DESIGN.md`.

Beneath that frozen surface, the full registry is a GENERATED artifact
rather than a hand-curated list: a macro-level walker over the C++ config
headers, joined with a transcription of every shipped Nexus control, merged
by explicit curation rules into `tools.json` — 277 tools in 19 feature-area
groups, 427 deliberately-not-exposed leaves each recorded with its reason
(credentials, endpoints, the master switch, kwinrc companion writes, no
shipped control...), and every tool citation-verified individually (the
cited C++ line contains the property; the cited UI line accesses the key),
with drift guards in the test suite (count pins, all-cited-lines
re-verification, regeneration byte-identity). The rationale is §1's,
applied mechanically: a rule that anyone can re-run beats a list anyone
must re-trust, and "exposed because a shipped control grounds it, otherwise
not — with the reason" is auditable in a way a per-key judgement call is
not. The frozen 18 tools and their natural-language grammar are preserved
byte-for-byte; the other 259 tools are addressed by name (`--call`), which
keeps the NL surface small, testable, and honest — no silently grown noun
grammar.

The in-shell half is a native-QML decision: `shell/services/SettingsTools.qml`
is a QML singleton, not a Python bridge, because every Nexus page already
writes `GlobalConfig.<path> = value` property assignments auto-persisted
by ChangeBatcher — so the service reuses the shell's own write path
in-process, with no runtime Python dependency, no process spawn per tool
call, and an in-chat confirm card that only native code can render; the
registry stays single-sourced by embedding `tools.json`'s tables verbatim
into the QML with a Python test asserting byte-identity. Honesty line that
belongs to the record: every one of the 277 tools' citations was verified
per-tool, but the QML itself was not compiled or run — no Qt toolchain
exists in the build environment — so its guarantees are the static guards
(byte-identity, balance checks, API-surface pins) until a maintainer loads
the shell.

## 8. The EXPLAIN verdict's ToolSpec leak (bug, not feature)

`settings.explain.explain()` returned the matched `ToolSpec` dataclass
inside its result dict. Every text consumer ignored that key, but the
cortex `route --json` surface and the brain bridge's `json.dumps` both
serialize the whole explain answer — so any why-question that resolved to
EXPLAIN crashed with `TypeError: Object of type ToolSpec is not JSON
serializable`. The fix is at the source, not at the two JSON boundaries:
`explain()` now attaches `_spec_json(spec)`, a field-by-field flattening
that mirrors the tools.json row — the same explicit-dict discipline the
PLAN verdict's candidates use — so every consumer (CLI, bridge, future
script) can serialize the answer as-is. Regression tests cover the cortex
CLI, the bridge, and the settings-layer contract itself.

## 9. Genius domains as sidebar TOOLS, not a rival brain

The maintainer's direction on issue #120 is explicit: reuse the shell's
existing tool-call harness ("utilize the predefined agentic tools in
caelestia if you want") rather than building a second, competing system.
The most useful deterministic capability this repository owns is the
genius layer, and the sidebar's registry already has an extension point
shaped for exactly this — the `caelestia_setting_*` meta-tools. So five
genius domains (math, stats, logic, decide, palette) ship as
`caelestia_genius_*` registry entries in `AiAssistant.qml`, dispatched
through the assistant's JSON bridge — the same one-request-in,
one-response-out contract the brain already documents for QML callers.
This answers 0xSolanaceae's skepticism directly instead of rhetorically:
the Ollama model stops being the calculator. "What's 15% of 840" is
`840*0.15` run by a parser with an evidence trail; "which of these two"
is a TOPSIS ranking with its separation table; a proposed accent color
gets a WCAG contrast verdict before any scheme suggestion. Every answer
is provable in a demo, deterministic, and reproducible — the property a
plain LLM wrapper cannot offer.

Scope discipline, from the same thread: only the priority-1 domains plus
palette (priority 2) ship in this round, because each needs its registry
entry, dispatch handler, and args-parity guard reviewed by a small
volunteer team with this work explicitly backlogged. The dispatch spawns
one short-lived `caelestia-assist api` process per call — the same
pattern, and the same trust boundary, as the existing `caelestia_command`
and `web_search` tools (spectacle, magick, python3 are already trusted
bins); the ops are read-only and allow-listed, so the spawn adds no new
write path, no network surface, and no execution capability. No new
top-level package is warranted: the bridge op lives in the existing
`brain/bridge.py`, the dispatcher in the existing `genius/decision.py`,
the tests in the existing suites, and the QML change extends the file
this repository already patches. Deliberately left out: `cortex_recall`/
co-change QML surfacing (needs a proactive-card design worth its own
review round), everything in `sysintel.py` (never asked for in the
thread), and any auto-apply path (the ledger and confirm cards stay the
only writers).

## What was deliberately not done

- No training or fine-tuning (not enough data; unnecessary for the scope).
- No pip dependencies, no embeddings, no network index.
- No changes to the shipped shell's own CLI (`caelestia`, `caelestia-color`)
  or to any shipped QML beyond the two files this repository deliberately
  patches (`AiAssistant.qml`) and adds (`SettingsTools.qml`) — both left as
  unreviewed, separately-reviewable diffs for the maintainer's own pass; the
  four troubleshooting layers touch no shipped shell code at all.
- No push, no pull request, no issue filed: the work is a local, unreviewed
  checkout on top of `dev` — untracked `assistant/`, `tests/test_assistant.sh`
  and the two shell-file changes, no commits, no branches.

## Known gaps left for human review

- Doc anchors are normalized to exact GitHub slugs — every rule anchor
  resolves to a real `TROUBLESHOOTING.md` heading.
- The import scan cannot, in principle, catch aliasing/getattr evasion; the
  operative guarantee is that the reviewed code contains none (grep-verified)
  plus the allow-list as a tripwire.
- Corpus issue text is captured verbatim; future captures should be screened
  for prompt-injection content at corpus-build time before Layer 3 consumes
  them.
- Settings layer: no per-monitor override support (the global `shell.json`
  only, with a read-only shadow warning).
- The in-shell ConfigManager/tool API that #120 sketches now has an
  implementation as a native QML service (`shell/services/SettingsTools.qml`
  wired into `AiAssistant.qml`), unreviewed and statically guarded only —
  the QML was not compiled in the build environment, so runtime
  verification and the accept/reject decision remain the maintainer's.
- The framing question for the maintainer: #120's sketch (an in-shell tool
  API) and this repository's reading (an external tool writing the watched
  file, validated by the shell's own reload path) are both defensible
  readings of "never modify configuration files directly" — this
  repository now ships both readings (the QML service writes via
  `GlobalConfig` property assignments; the offline CLI writes the watched
  file), and which one Caelestia wants is a design call that belongs to the
  maintainer, not to this branch.
