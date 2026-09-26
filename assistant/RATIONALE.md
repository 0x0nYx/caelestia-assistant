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

## 10. The verbless front door and inline delegation (routing fix)

The assistant used to require the user to know which of 18 verbs their
question belonged to before it would parse anything: a first token that
matched no `ROUTES` key exited with code 2. That is a CLI-shaped contract
imposed on a natural-language surface, and it failed exactly the users
issue #120 is about — the person who types `caelestia-assist "make my bar
thinner"` and has not read `--help`. The fix has three parts, each a
generalization of machinery that already existed, not a new mechanism.

**1. Verb tolerance (hub.py).** An unmatched first token is no longer an
error. Within edit distance 2 of exactly one verb (the settings CLI's own
forgiveness bound, `settings --tool setBarPositin` → "did you mean
setBarPosition (distance 1)"), the hub prints the same style of
suggestion to stderr and exits 1 — a prompt, never a silent guess; ties
and sub-5-character tokens abstain to the free-text path (the router's
own min-length and unique-correction discipline, applied at hub scope).
The distance computation is `cortex/lexicon.py`'s `levenshtein` — the one
implementation the router's query-side correction already uses — so no
second edit-distance exists in the codebase. Everything else is free
text: the whole argv becomes one request through the cortex pipeline
one-shot, which is read-only and renders an answer, a pending plan, or a
simulated agent plan. A leading `--` separator is honored and stripped,
and a phrase that begins with a dash is passed past argparse's option
parser with an explicit `--` guard — free text is never parsed as flags.

**2. Inline delegation (cortex/delegate.py, cli.py).** The chat REPL
already ran genius inline instead of printing a "try:" hint; that branch
is now a table. Every DELEGATE category with a read-only entry point —
genius (`meta.route_and_do`), diagnose (`engine.diagnose`), search
(`retrieval.search.search`), brain (the brief — its synthesized answer to
plan/focus-shaped requests), issue (a draft *preview*: without `--confirm`
the issues module writes nothing, its own documented contract) — runs in
the same turn, in both places the branch existed (the REPL loop and the
one-shot `route` command), kept consistent the way genius already was. A
runner failure degrades to the old hint card with an honest note; the
"try:" strings survive as the fallback, not deleted. Nothing in the table
adds a write path, a subprocess, or an import: ALLOWED_IMPORTS.txt is
byte-identical before and after, and `selfcheck` stays green.

**3. The agent delegate.** A fifth category, `agent`, extends the
router's cue-lexicon and structural floors — the same mechanism that
distinguishes settings from genius from search — rather than a second
classifier. Two conditions must both hold: sequencing grammar on the
full text ("... then ...", "after that", "first ... then", "step by
step" — `router.AGENT_SEQ_RE`, floored at 0.84 like the genius pattern)
AND boundary crossing (at least one clause the settings surface cannot
address; checked before the compound splitter shreds the sequence,
because for "clean my downloads then make the shell minimal" the ORDER
is the request). Pure settings sequences keep their compound behavior:
"disable blur then make animations faster" is still two ops in one gated
plan. The runner calls `agent.cli.main` with `--simulate` only; the
agent's execute path (and its stdin consent gate) is unreachable from a
conversation — turning a simulation into action stays a manual step,
same contract as `RATIONALE §5` (round three). Single-clause goal
phrases ("clean up my downloads folder") reach the same delegate through
the seeded agent surface doc, whose vocabulary is deliberately disjoint
from the brain doc's note-taking words so "organize my notes" stays a
brain request.

**4. The sidebar's local-vs-cloud decision.** `cortex.dispatch` — the
single decision point, never the sidebar's QML — now answers runnable
DELEGATEs locally: the inline runner's output becomes the sidebar bubble
(`outcome.answer`), and no gap is logged because the local ontology
answered. Only a non-runnable delegate or a FAILED inline run hands off
(reason `delegate:<surface>-inline-failed`, a countable category), and
ABSTAIN / below-conformal-threshold hand-offs are untouched. The QML
itself needed no change: it already renders `outcome.action`/`answer`,
which is the architecture working as designed.

Safety accounting for the whole fix: zero new write paths (the one write
in chat remains the y/N-gated applier call; the one write in the bridge
remains the state/ledger persistence the caller already owned); zero new
imports; no auto-consent of any kind; the issue draft stays a preview;
the agent stays simulated. Interaction edges touched: none against the
shipped shell — no settings tool, QML property path, or doc anchor was
changed, so no new citations are claimed.

## 11. The filesystem second-brain (genius/fsbrain.py)

Issue #120's "second brain" direction needs a filesystem intelligence
layer that is honest about being classical. Four analyses, each a
generalization or reuse of machinery that already shipped:

- **Staleness/entropy**: `sysintel.analyze_history`'s frecency formula
  (`1 + 0.5^(age/half_life)`) generalized from shell-history event
  positions to `stat()` event times (mtime = write, atime = read);
  directory entropy is Shannon bits over the category mix. A
  tidy-style REPORT — propose-only, never moves or deletes anything
  (`brain.tidy`'s journaled apply/rollback path stays the only mover).
- **Near-duplicates**: metadata fingerprints (name/suffix/size-bucket/
  mtime-day) through `scan.simhash` with its own digit masking, then
  the crawler's banding trick (Manku, Das & Sarma 2007) for candidate
generation — O(n) buckets, not O(n²) pairs — and Hamming ≤ 3
  verification at `scan.simhash`'s documented operating point.
- **Knowledge graph**: TF-IDF words (`brain.textmine.keywords`, corpus
  = the other docs — the extractor's own semantics) plus RAKE phrases
  (`genius.language.rake_keywords`), an unweighted co-occurrence graph
  built THROUGH `brain.personal.graph.Graph` so its PageRank and
  label-propagation communities run verbatim — no second
  implementation of either, no embeddings, nothing trained.
- **File-type inference**: the classic magic table through
  `scan.ac`'s Aho-Corasick automaton, offset-anchored so a "PK" deep
  in a text file never claims zip; misses fall to an
  online-correctable multinomial Naive Bayes
  (`brain.naive_bayes.NaiveBayes`) over byte features that starts
  EMPTY and learns only from user corrections — persisted as a
  bounded list of reviewable docs (features + human label) in the
  brain state, never a model blob.

**Event-driven watching — deliberately NOT shipped.** The §5 invariant
(reactivity must be event-driven, never a sleep-loop) was audited
first: the codebase contains zero sleep-loops and zero pollers (every
scan is a user-invoked one-shot; steady-state idle RSS is zero because
nothing is resident). The prompt's suggested primitive — "inotify via
stdlib os/select" — was then measured before being trusted:
`select()` on a directory fd is ALWAYS reported readable on this
platform (verified live: an untouched directory selects ready
immediately), so any watch built on it degrades into a getdents poll
loop — the exact pattern §5 forbids. The real inotify(7) route needs
`ctypes`, which ALLOWED_IMPORTS.txt rejects by name. The honest answer
is no watcher at all: nothing in this design needs one, and a fake
"event-driven" loop that secretly polls would violate the invariant it
claims to satisfy. Recorded in Known gaps below.

Safety accounting: read-only analyses (tests compare directory bytes
before/after); bounded walks (the sysintel max-files discipline); one
write path — filetype corrections persisted through the brain state's
existing atomic save, bounded at 500 docs. No new imports beyond the
existing allow-list; no interaction edges against the shipped shell.

## 12. New genius domains (phase 2.2)

Five additions, each a named classical algorithm with a citation in the
code, no dependencies, no training:

- **Graphs, first-class**: the `genius graphs` front door now exposes
  dijkstra/astar/topsort/mst/assign (previously dijkstra lacked astar in
  the CLI) plus Edmonds-Karp max-flow with the min-cut by the
  max-flow/min-cut theorem (Edmonds & Karp 1972), and label-propagation
  communities (Raghavan et al. 2007) — the communities function ADAPTS
  the caller's adjacency into `brain.personal.graph.Graph` and runs its
  existing deterministic implementation verbatim rather than forking a
  second label-propagation. A `graph_algorithms` meta domain routes
  natural-language graph requests to a capability card.
- **Resource-contention scheduling** (`logic.schedule_resources`): the
  settings layer's AC-3 runs over settings keys; this is the SAME CSP
  machinery lifted to the general shape the agent layer needs — tasks
  contend for named resources over discrete slots (per-resource
  all-different + precedence arcs + time windows), solved by AC-3 then
  backtracking with MRV + forward checking, with the pruning trail
  reported as evidence. settings/optimize.py is untouched: both surfaces
  sit on the one CSP implementation.
- **Branch-and-bound** (0/1 knapsack with Dantzig's fractional bound,
  Land & Doig 1960) for small integer programs; cross-checked against
  exhaustive search on randomized instances in the tests.
- **Tabu search** (Glover 1986) — deterministic order, recency list,
  aspiration override — for scheduling-shaped permutation problems; the
  CLI exposes the switch-cost form, the API takes any score/neighbor
  pair.
- **NCD** (Li et al. 2004) over zlib/bz2 — the compressor IS the
  similarity model, which is exactly the honest fit for a no-ML
  assistant; bz2 joins ALLOWED_IMPORTS.txt as a documented,
  same-class-as-zlib pure compression module (the import tripwire fired
  on the first version — the policy enforcement works, and the addition
  is a one-line named exception, not a relaxation).
- **BOCPD** (Adams & MacKay 2007) as the probabilistic complement to
  the existing bootstrap-CUSUM: run-length posterior, constant hazard,
  conjugate normal segments, the differences-based noise-scale default
  (insensitive to the shifts being hunted). One implementation bug was
  caught by testing against a ground-truth shift (the changepoint arm
  must use the PRIOR predictive, not the segment mixture — the classic
  mistake) — the tests pin the corrected recursion.
- **STL-lite robustness** re-checks: the same decomposition estimator
  under period±1 and a 10%-trimmed seasonal pass, reporting trend sign
  agreement (with a flatness epsilon so noise around a constant trend is
  not counted as disagreement), seasonal-amplitude and residual-sd
  stability, and a verdict that carries its numbers.

Safety accounting: all read-only computations over caller-supplied
inputs; no new write paths; no interaction edges against the shipped
shell.

## 13. Agent goal archetypes (phase 2.3)

Five new HTN methods on the SAME consent/simulate contract — no new
architecture, no relaxed gate:

- **config_hygiene**: `settings.lint` (the `--lint` rule set verbatim)
  + the brain's preference-posterior drift report; reconciliation
  PROPOSES reset-to-default ops that go through the standard
  planner/applier gate. One honest limit is pinned by test: a
  TYPE-mismatched key is a MANUAL instruction, never a bypass — the
  planner's own doctrine ("never a silent cast or structural repair")
  is honored, not worked around; out-of-range values (typed, wrong
  magnitude) do repair through the standard path.
- **package_audit**: `agent/pkgprobe.py` — the FIRST quarantined
  subprocess module, exactly the DBus proposal's pattern: the import
  policy gains a per-module carve-out (pkgprobe.py alone may import
  subprocess; a test pins the exemption set to exactly that one entry,
  and another test proves a subprocess import anywhere else still
  fails the lint). Fixed argument arrays (`pacman -Q`,
  `dpkg-query -W`, `flatpak list`), read-only queries only, bounded
  timeout, kill-switched OFF by default in the capability manifest,
  and matched against a STATIC local keyword list — deliberately not
  a CVE feed: no network, no version freshness claims.
- **log_triage**: sysintel's Drain-style template mining + z-score
  anomalies composed directly into `issues` drafting (preview only,
  `--confirm` stays the user's) — the two packages that never talked.
- **notification_triage**: the PURE classifier (per-source frequency +
  Laplace-smoothed acceptance rate, the beta-posterior shape the
  bandit layer already uses; batch = high-frequency AND
  low-acceptance). The live DBus OBSERVATION surface is deliberately
  NOT implemented: it requires the quarantined DBus surface (a
  maintainer sign-off per that proposal's own escalation clause) plus
  a bounded `dbus-monitor` watch — recorded as a known gap rather
  than forced.
- **screenshot_diff**: pixel-REGION hashing (grid block-mean hashes,
  the aHash family) between two PNGs through the ONE PNG decoder
  (palette_extract.png_grid, refactored so png_pixels and the diff
  share it — no second reader), region rectangles merged, chained
  into issue drafting. NO OCR anywhere, by the invariants' explicit
  exclusion; the honest gap is stated in the draft itself.

**The capability manifest** (`assistant/capabilities.py`): the
per-install, user-editable switchboard every new surface registers
in — read-only zero-risk defaults ON, everything that shells out or
extends the import surface defaults OFF, flip-only-by-file-edit (an
NL request can never enable a capability), surfaced as
`caelestia-assist capabilities`.

**Engine bug fixed en route**: results were stored under node ids
(n1, n2, ...) while the downstream dispatchers composed from action
names ("match", "retrieve") that never existed — the composition
chains (fix_plan, explain, and the new drafts) silently always took
their fallback paths. Results are now addressable by BOTH node id
and action name; the new archetypes' tests pin the composition
actually happening.

Safety accounting: one quarantined subprocess module (off by
default, fixed arrays, read-only, pinned by test); one consented
write path that IS the existing applier; everything else read-only;
no interaction edges against the shipped shell changed.

## 14. Self-learning upgrades (phase 2.4)

- **LinUCB** (`brain/preset_bandit.LinUCBBandit`): the contextual
  bandit (Li, Chu, Langford & Schapire 2010, disjoint model) beside the
  context-blind NamedBandit — d x d Gram matrices updated by outer
  products, exact UCB bound, Gaussian-elimination solve, pure
  arithmetic, no library. The reward-shape test pins the paper's update
  equations; the context test pins that the SAME preset ranks
  differently under morning vs evening contexts. NamedBandit is
  untouched (byte-identical reward semantics, pinned).
- **Shared feature hashing** (`brain/features.py`): the hashing trick
  (Weinberger et al. 2009) with signed collisions and L2
  normalization — ONE input-space all learners agree on (router,
  genius, presets) while their STATE stays separately auditable:
  transfer without merging, the boundary RATIONALE already drew.
- **Ebbinghaus half-life, user-editable** (correctness fix for
  multi-user installs): the memory decay constant moves from a module
  constant to the brain state (per-user by construction, bounds
  0.5-365, garbage degrades to the default), read/set via
  `cortex halflife [DAYS]`, threaded through recall and follow-up
  weighting. History untouched — only future weighting changes.
- **The shared ranking primitive** (`brain/ranking.py`): Elo (online)
  + Bradley-Terry (batch logistic fit, deterministic gradient ascent)
  + Kendall-tau agreement between them, over ANY named items — the
  generalization of the preset-ranking proposal. The proposal's own
  verification plan is the test: synthetic 300-pair recovery against
  ground-truth strengths (exact ordering), sparsity honesty (<3
  comparisons = "not enough data"), determinism. Consumers: presets
  (`settings --prefer A B` records one deliberate comparison after
  side-by-side DRY-RUN previews; `settings --rank` reads the ladder)
  and agent plan comparisons (the same functions, separately-keyed
  records).
- **Calibration surfaced**: the chat card and the sidebar answer now
  carry "routes scored like this one were right ~N% of the time (k
  decisions)" — the OBSERVED acceptance rate of the route's
  confidence bucket, only when >= 5 decisions support it (small
  samples say nothing; silence beats a fake number). The bucket key is
  the RAW route probability (learn_hook), not the calibrated
  confidence — a distinction the tests pin.

Safety accounting: all learners stay read-only rankers over
human decisions; `--prefer` writes one comparison row to the assistant
state (never shell.json); nothing new executes, imports, or reaches
the network.

## 15. The pending plan cache and the what-if consequence view (2.5/2.7)

- **The plan cache** (`cortex/plans.py`, phase 2.5): one session-scoped
  PENDING plan, composed by TOOL NAME with LATER WINS — the compound
  layer's own rule, so "make the bar thinner", "and the dock smaller",
  "actually spacing tighter" amass changes before any commit. The
  composed list re-validates through the STANDARD planner before it is
  ever proposed (the cache never bypasses validation); commit happens
  only when an apply actually went through, and a REFUSED apply leaves
  the ops pending — that is the point of iteration. Discard is explicit
  ("never mind" / "start over" / "drop it"), never silent. The cache
  is a pure module serialized through the session dict the bridge
  already round-trips; bounded at 12 ops.
- **The consequence view** (`settings/consequences.py`, phase 2.7 per
  proposals/2026-09-26-c-whatif-consequences.md): a HAND-CURATED,
  citation-backed table of five KNOWN cross-key interactions in the
  shell's own code (transparency-off flips blur off; blur is inert
  without transparency; bar scale clamps at 0.6 at render time; dodge
  is inert without persistent windows; bar padding floors at
  Tokens.padding.small). The projection walks that table over a
  candidate op list and returns derived effects the user did NOT ask
  for — each with its citation and confidence — plus the AC-3 view
  (requested values against registry domains) and the induced-value
  extension: an edge that forces a value the user contradicted
  ("transparency off" + "blur on") is a reported conflict, cited to
  the handler that wins.
- **The honesty rule**: the consequence universe is EXACTLY the cited
  edge table — bounded, auditable, growable by reviewed diffs, never a
  general model. Every edge's cited file:line is re-verified against
  the checkout by test (the registry's citation-guard pattern,
  extended); a stale edge is a test failure, never a silent surprise.
  An edge whose effect only ANNOTATES (INERT/CLAMP states that change
  no shell.json value) carries no machine value — it cannot lie to the
  conflict check.
- **Surfaces**: `settings --what-if TEXT` (a request or a preset name)
  renders the view read-only; the chat loop's "what if ..." turn
  composes the request with the pending plan and projects it; the
  agent engine's validate_plan node carries the same dict so
  `--simulate` consent cards show consequences, not just actions.
- **Step ops project as resolved values**: the projection runs over
  the planner's RESOLVED entries — "make the bar smaller" projects
  bar.scale 0.9, never the raw step delta of -1 (the bug this pins
  fired the 0.6-floor edge on every relative request). A bare "what
  if" projects the pending plan itself and never routes a placeholder
  phrase (the router's fuzzy match once turned "show my pending
  changes" into a toast toggle and polluted the pending plan).

Safety accounting: the consequence view is a VIEW — it reads op lists
and the edge table, writes nothing, and the parser/planner/applier
spine is untouched; the plan cache composes ops but every composed
plan still passes the standard consent gate (dry-run by default,
backup + bounded undo on apply). A latent chat-exit crash
(`log_review_candidate` stored the live `_now()` datetime raw and
`brain_state.save` raised on JSON serialization) was found by this
work and fixed by coercion at the boundary; a regression test pins
the clean exit.

## 16. The DBus surface (phase 2.7's DBus half, quarantined)

`settings/dbus_surface.py` implements the proposal
(proposals/2026-09-26-c-dbus-surface.md) with the quarantine the
proposal itself demands: the second (and only other) module permitted
to import `subprocess`, through the per-module carve-out
`_QUARANTINED_IMPORTS` in `diagnostics/schema_lint.py` — pinned to
exactly {pkgprobe.py, dbus_surface.py} by tests in three suites. Every
other module keeps the zero-tolerance rule. The maintainer decision
the proposal escalates stays honest: the surface ships DISABLED
(capabilities.json `dbus_surface: false`), enabled only by a file
edit, never by a request.

- **The catalog**: five fixed commands — kwriteconfig6 (Night Color
  master switch; the lock-screen timeout, the target repo's own
  CONTRIBUTING precedent), kscreen-doctor (mode change from the
  OBSERVED topology), powerprofilesctl (set one of the OBSERVED
  profiles), and one irreversible dbus-send KWin script unload. IDs,
  binaries, risk classes, and reversibility are pinned by test; adding
  one is a reviewable diff.
- **Fixed argument arrays**: every spawn is
  `subprocess.run([binary, *fixed_args])` — never `shell=True`, never
  free-text interpolation. Values fill typed slots (bool/int with
  catalog bounds) or are machine-derived from a prior READ (the
  kscreen pair {output, mode} must come from the parsed topology; the
  power profile from the parsed table).
- **Risk discipline**: nothing above STATE_CHANGING is cataloged; the
  execution path guards against PRIVILEGED/DESTRUCTIVE anyway (a
  future edit cannot silently bypass review — the pinning test fails
  first).
- **Undo where the tool supports it**: kwriteconfig6 writes read the
  previous value first (kreadconfig6, same fixed shape, coerced back
  to the slot's type so the record round-trips validation); kscreen
  writes capture the observed prior mode for the same output; power
  profile sets capture the prior active profile. `apply_undo` performs
  exactly one inverse write per record — bounded, never a replay
  loop. The KWin script unload is cataloged IRREVERSIBLE, produces no
  undo record, and refuses to run without an explicit
  `confirm_irreversible=True` (the proposal's second confirmation).
- **Library surface, not conversational**: no NL request reaches it
  and no CLI route applies a write — the caller renders
  `plan_write` (the dry-run artifact works even while disabled), shows
  it, obtains consent, then calls `run_write`. The read probes
  (`read_kscreen_outputs`, `read_power_profiles`) parse the tools'
  own output into machine-derivable values.
- **Tests**: 26 unit tests against a FAKE spawn (recorded calls, no
  process): argv shapes, the kill-switch (nothing spawns while
  disabled — reads AND writes), value validation and catalog bounds,
  undo round-trips, the irreversibility gate, lint parity. The real
  KDE-session integration test stays behind
  `CAELESTIA_ASSIST_DBUS_TESTS=1`, never set in CI — the proposal's
  own gate.

Safety accounting: OFF by default (capability kill-switch, file edit
only); quarantined import (second of exactly two modules, pinned);
fixed arrays; observed-only values; no DESTRUCTIVE commands cataloged;
bounded one-write undo; the belt-and-braces AST scans in
settings/tests/test_safety.py learned the quarantine so every OTHER
module still fails on `subprocess`.

## 17. Lexicon-diff sharing and the generation adapter (phase 2.6)

- **The lexicon diff** (`cortex/lexicon_diff.py` + `cortex lexicon
  export|import|forget|list`): a plain-text, reviewable list of
  `phrase -> tool` mappings a user's cortex learned — capped at the
  newest 200, PII-stripped to the undo log's standard (no timestamps,
  no file paths, no values; phrases are the only content). "Federated"
  means the artifact travels the channels the community already uses
  (issues, matrix, fork PRs) — NO server, NO network code, NO crypto
  code in the assistant. "Signed" happens OUTSIDE (minisign/sq/GPG
  over the canonical text): the assistant states the content, the
  human owns the trust in the identity.
- **Import safety** (the proposal's mitigations, pinned by test):
  import caps (200), per-phrase length cap (120, the learner's own
  bound), unknown tools / unparseable lines / duplicates /
  over-cap rows import as no-ops with WARNINGS, never exceptions
  (the injection-fuzz contract); the import report lists every tool
  the diff boosts; rollback is one command (`forget <diff-id>`,
  content-addressed by sha256 of the canonical rows).
- **Where imports land**: as SUPERVISED PAIRS in A2's embedder seam
  (``PpmiEmbedder(labeled_pairs=...)`` — the shared singleton reads
  the persisted pairs at its lazy first build; an ABSENT import keeps
  the corpus-only build byte-for-byte, which is why the fingerprint
  test still pins the no-pairs build) and as REVIEW-BUCKET candidates
  for the learner's batch flow — never into the hand-seeded SYNONYMS
  (that table stays a reviewed diff).
- **The generation adapter interface**
  (`settings/gen_adapter.py` + `python3 -m assistant.settings
  gen_adapter [--verify]`): the registry-generation contract
  formalized — ONE canonical serialization (``canonical_bytes``:
  every producer and every comparison goes through the same
  rendering, so byte-identity is a property of the pipeline, not a
  per-caller convention); a REGISTERED adapter table (name -> build
  callable, pinned to the shipped ``cpp-headers`` walker); a
  structural SCHEMA check third-party output must satisfy; and
  ``verify`` — the drift guard as a read-only function (build, render,
  compare, report the first differing lines; never writes). The
  committed tools.json verifies byte-identical through this seam
  today.
- **The capability manifest** grows `lexicon_sharing` (ON by default:
  CLI-only, offline, no network, import is an explicit user command
  with rollback) — a community deployment can turn sharing off
  entirely with one file edit, the same posture as every other
  capability.
- Two lint gaps closed while building: the import-policy AST walk
  treated the absolute form of intra-package imports
  (`import assistant.x.y`) as forbidden while allowing the `from`
  form — now both forms skip the assistant root (the target module is
  scanned by the same walk); and the brain state gained the
  `CAELESTIA_BRAIN_STATE` path override (the same override pattern as
  the capability manifest) so tests and sandboxes never touch the
  user's runtime state.

Safety accounting: no network surface (nothing in assistant/ can
transmit — the user moves the text themselves); imported phrases are
router supervision, never instructions (a malicious diff can at worst
skew routing toward wrong tools, bounded by the AMBIGUOUS/consent
gates); generation is a build-time developer act — the runtime
registry loader is untouched and never executes generator code.

## 18. Agency without autonomy creep (the agent, scan, and optimizer design)

*(Written in the round that first shipped the agent layer; kept verbatim — the design holds.)*

The agent (`assistant/agent/`) was designed against the failure mode the
layers above exist to prevent: an "AI that does things" that quietly does
them wrong. Three choices follow from that. First, decomposition is
hierarchical and deterministic (HTN methods over cue-classified goals), and
the graph is *projected* (`--simulate`) before anything runs — the plan is
an artifact the user reads, not a hidden process. Second, consent is
per-node and structural: a node above READ_ONLY risk carries
`consent_required=True` and the engine refuses to run it without a True
from the caller; there is no "trust me" flag, and no PRIVILEGED or
DESTRUCTIVE node type exists at all — that work stays an inert suggested
string. Third, learning observes outcomes (accepted / refused / failed /
skipped) through the same ledger-shaped signal every other learner uses, so
the agent gets better at proposing exactly what you approve — and the
preference model, conformal layer, and drift detector make that improvement
auditable instead of mystical.

The scan layer exists because the honest bottleneck on a low-end machine is
memory, not intelligence: Aho-Corasick makes signature scanning O(stream)
regardless of rule count, and the probabilistic structures (Bloom, Count-Min,
HLL, reservoir) give provable-bounds answers under fixed RAM where exact
answers would require loading the file. The settings optimizer keeps the
#120 contract intact — Pareto fronts and AC-3 constraint propagation
*propose*, the planner *validates*, the applier *gates* — because an
optimizer that could write directly would be the most dangerous code in the
repository.

## 19. Exponential-build sessions (safety accounting per shipped sub-item)

*(One shared section for the second exponential-build run; one dated
subsection per phase, appended as sub-items ship. Each paragraph is the
safety accounting the operating prompt requires before a sub-item may
commit.)*

### Phase 1 — cortex routing intelligence (2026-09-27)

**1.1 gap-cluster → tool-template stubs.** `cortex gaps` gains an
explicit `--draft-stubs` flag: a dense cluster (the same support ≥ 3 /
purity ≥ 0.6 floors the clustering always had) that the ledger holds NO
item for — pending, approved, or rejected; the ledger flow IS the
address — can be drafted into a reviewable `.md` stub (name, cue words,
TODO body) under `~/.local/state/caelestia-brain/tool_templates/`
(`--stubs-dir` overrides). Safety accounting: the drafting functions in
`cortex/dispatch.py` are pure (the module still writes no files itself —
the CLI owns the write, exactly as it owns state writes); the stub
format is markdown, so nothing can import or execute it; the stub
marks itself DRAFT and is never registered in the router, never wired
into the dispatcher, never added to the registry (pinned by test); an
existing stub file is never clobbered (it may carry human edits —
pinned by test); a draft-only run writes no ledger and does not mutate
the learned state (pinned by test); selection runs before `--propose`
files its proposals so one run can do both without the drafter and the
ledger disagreeing about what is addressed. The stub says plainly what
the project says everywhere else: the requests keep falling through
honestly until a human writes the named classical algorithm behind the
template.

**1.2 undo-weighted calibration.** The settings undo log (the A3
PII-stripped negative store) gains one boolean per record — `quick` —
computed AT UNDO TIME from the bounded 12-entry ring itself: the undone
apply was still the ring's head, i.e. an immediate revert with no later
apply in between. No timestamp, label, value or text is stored, so the
strip rule's promise ("cannot identify a person, a file, or a time")
still holds — a relative fact about the interaction, not a clock
reading. `calibrate.fold_undo_negatives` is the same Beta-Binomial
update it always was; a quick record simply contributes
`QUICK_UNDO_WEIGHT = 4.0` beta units instead of 1.0, and 4.0 is the
smallest integer weight whose arithmetic satisfies the requirement the
operating prompt pins: with the Beta(1,1) prior, approve-then-quick-
undo lands at mean 2/7, strictly BELOW a plain reject's 1/3 (w = 3
exactly ties; the boundary is pinned by test). A slow undo keeps the
plain weight — it cancels the approval it reverts (mean 2/4 = 0.5) and
no more, so the old conservative behavior is unchanged; pre-quick logs
fold exactly as before. Both two existing record-shape pins were
updated (not deleted) to pin the new shape, the same discipline the
previous session used when behavior explicitly changed.

**1.3 BOCPD drift on routing accuracy.** The example log's rolling
hit-rate (acceptance over overlapping 5-outcome windows, arrival
order — the same series shape the numeric telemetry feeds its
detectors) now runs through `genius.data.bocpd` (Adams & MacKay 2007),
the ONE existing BOCPD primitive — lazily imported exactly the way
`dispatch.py` lazily imports the k-means, and pinned by a spy test so
a second implementation cannot quietly appear. A real shift in routing
accuracy is therefore flagged the same honest way a shift in CPU load
is: the changepoint probability is REPORTED with its threshold and the
segment means before/after travel with it, nothing acts on it (a
report, not an action — `drift_check`'s halves heuristic stays
untouched beside it as the deterministic view). Thin data is labelled
`insufficient-data` and invents no numbers (BOCPD's own n ≥ 4 floor
does the gating); the whole path is deterministic.

**1.4 discriminative re-ranker.** `cortex/reranker.py` mirrors the
slot_tagger's structural template exactly: an averaged pairwise
max-margin perceptron (Rosenblatt 1958's update over Herbrich,
Graepel & Obermayer 2000's pairwise ranking formulation; Collins 2002
averaging) over the router's OWN per-candidate signal components —
`RouteResult.features` already carries lex/sem/fuzz/noun/cue/coverage,
so no second feature implementation exists. Supervision comes only
from local routing history, with the slot_tagger's rules verbatim:
approved rows give one constraint per competitor (the accepted surface
must outrank what the router scored alongside it), rejected rows give
nothing, a surface the router never scored fabricates no constraint.
The gate is the repo's ONE uncertainty mechanism: top1-vs-top2 margin
→ the same fixed-scale logistic class → `ConformalCalibrator.verdict`;
untrained model, single candidate, below-threshold confidence, or no
calibration data all return the router's OWN ranking unchanged with
the reason attached — the re-ranker adds preference, it never guesses.
Like the slot_tagger, it ships as a library + gated entry point with
persistence into learned-state JSON; the live pipeline is untouched
(that wiring is the maintainer's call once the calibrator stream for
this signal accumulates), deterministic end to end, no I/O.

**Phase 2 — genius new domains (2026-09-27)**

**2.1 tiny inductive program synthesis.** `genius/synth.py` (plus a
read-only `genius synth` CLI verb) implements FlashFill-style
trace-based synthesis (Gulwani 2011) over a deliberately tiny DSL:
1-3 stages of prefix/suffix/between/head/tail extractions joined by
constant strings, delimiters harvested from the examples themselves.
Safety accounting: a candidate program must reproduce EVERY example
exactly — the inductive check is the honesty mechanism, and anything
the DSL cannot explain (one example, four examples, a letter/digit
boundary the DSL cannot express) is an explicit abstain, never a
guess; genuine ambiguity (several expressions coincide) is reported
with a count, the canonical fewest-stage answer never hides it;
`apply_program` refuses rather than fabricates when a stage reads an
input the caller did not supply; the ONLY executable-looking output is
an inert `SUGGESTED_NOT_EXECUTED: [STATE_CHANGING] mv -n -- ...` line
the user copies themselves (shell-quoted, `-n` so it cannot clobber);
the module is pure string algebra — no I/O, no subprocess, no clock,
no RNG, deterministic end to end and pinned by test.

**2.2 stdlib CSV expression domain.** `genius/csvquery.py` (exposed
read-only as `genius data --csv ... --expr ...`) is a named-column
expression evaluator built entirely on existing primitives:
`data.parse_table` (the csv-module parser the data domain already had),
`stats.py` (describe/quantile/pearson for the aggregates), and `ast`
as the SAFETY mechanism — the expression is walked over an explicit
node whitelist and `eval` is never called; attribute access,
subscripts, lambdas, string constants and unknown function names are
rejected by name before anything runs. Honesty accounting: a missing
or non-numeric cell makes the surrounding row value None (Kleene
propagation through and/or/not) and lands in a reported
`rows_unavailable` count — never coerced to 0 or False; division by
zero is unavailable, not infinite; `quantile`'s q outside [0, 1] is
rejected, never clamped; an unknown column is an error that lists what
exists; `pearson` pairs rows positionally and refuses to claim a
correlation from fewer than 3 aligned pairs. No I/O in the evaluator —
the caller owns the table text — and the CLI path reads the user's
file and prints; it writes nothing.

**2.3 NCD file/folder resemblance.** `fsbrain` gains `ncd_resemble`
(pure core) + `resemble_file` (read-only wrapper) + the `fsbrain
resemble` CLI action: "which existing folder does this file most
resemble", answered by the ONE existing NCD primitive
(`genius/data.py::ncd`, Li et al. 2004 — spy-pinned reuse, no new
compressor, no new distance formula). Read-only accounting: the pure
core never touches the filesystem (the caller hands it bytes); the
wrapper only reads (bounded deterministic head samples, sorted walk,
unreadable files counted and named, never faked); folders without
readable samples are skipped and NAMED rather than scored a fake 1.0;
empty content is refused; compared files are head-truncated to a
documented cap with the truncation reported; the whole ranking is
returned (best + all distances), ties broken by folder name — the
answer is a report, and nothing is moved, written, or executed.

**2.4 resolution syllogism checker.** `logic.py` gains
`syllogism_check` (plus a meta.py hook: "therefore"-shaped arguments
route to it only when EVERY clause parses — anything else falls
through to the propositional path unchanged): premises + NEGATED
conclusion are refuted by binary resolution (Robinson 1965; Horn
1951 — every clause in this fragment is Horn, so no factoring is
needed and saturation is decidable). Honesty accounting: the empty
clause proves VALID, saturation without it proves INVALID (the
saturated set is satisfiable — the premises can hold while the
conclusion fails), both stated with the derivation evidence, never a
bare verdict; statements outside the well-formed fragment are honest
LogicErrors listing the accepted forms; the one normalization is a
deterministic, documented regular-plural rule (cats/cat) — irregular
forms like men/man stay distinct, and the test pins that the checker
does NOT pretend they resolve; no existential import is assumed
(modern reading: "no A are B" does not entail "some A are not B" —
pinned by test). Deterministic, pure, no I/O.

**2.5 commit-risk score for devflow.** `devflow/risk.py` (CLI:
`python3 -m assistant.devflow risk --source FILE < log.txt`) implements
McCabe's cyclomatic complexity per function from the stdlib `ast`
(1 + decision points, nested functions owning their own decisions)
multiplied by log2(1 + recency-decayed churn) from `git log --numstat`
text — the file rows reuse `diffstat.parse_numstat`, the ONE numstat
parser, and there is NO subprocess anywhere: the caller pipes the text
exactly as diffstat's input contract already established. Honesty
accounting: churn decays by commit recency with a fixed, stated
half-life (git's own newest-first order is the recency signal — no
timestamp parsing, no clock reads); the tier thresholds are stated
constants pinned by test; an unparsable source REFUSES the complexity
half (risk stays None, churn still reported) rather than scoring
garbage; the whole thing is a report for the human's review — nothing
gates, nothing blocks, nothing executes.

**2.6 robust Mahalanobis telemetry baseline.**
`diagnostics/robust_baseline.py` + `agent/archetypes.telemetry_drift`
(one more read-only evidence source for the config_hygiene
archetype): center = coordinate-wise median, scale = 1.4826 x MAD
(Leys, Klein, Bernard & Laurent 2013), distance = Mahalanobis with
that diagonal robust scatter (Mahalanobis 1936), p-value tail from the
EXISTING `stats.chi2_sf` primitive. Why robust: a mean/variance
baseline is poisoned by exactly the outliers it is supposed to catch —
pinned by a test where one poisoned history row moves a mean-based
center but not the median. Honesty accounting: degenerate coordinates
(MAD = 0, the metric never moved) are excluded and NAMED, never given
a fake scale; missing sample coordinates (no battery, no thermal zone)
are excluded and counted, never imputed; fewer than half the baseline
coordinates present in a sample is a REFUSAL, not an extrapolation;
thin history (< 8 rows) is refused up front; the chi-square p-value is
reported with its independence/normality caveat attached ("reported
not worshipped"); the archetype hook is evidence-only — nothing acts
on the verdict, the live path is the same one-shot /proc+/sys read-only
snapshot every other consumer uses, and battery capacity is
deliberately excluded from the metric vector (a cyclic quantity, not a
drift signal — documented).

**Phase 3 — brain self-learning (2026-09-27)**

**3.1 hierarchical partial pooling.** `brain/pooling.py` is the ONE
shared utility the operating prompt asked for: every new
preference/bandit posterior added from here on starts from the
population's hierarchical prior (Efron & Morris 1975) instead of the
flat Beta(1,1). Method-of-moments hyperparameters — pooled mean mu0,
between-arm variance tau², concentration k0 = mu0(1-mu0)/tau² capped
at full pooling when the arms agree and floored at one pseudocount —
all deterministic, all hand-checkable (the test pins k0 = 50/7 exactly).
Honesty accounting: the prior's own mass never counts as evidence; arms
without observed evidence are LISTED, never fabricated into the pool; a
pool with no evidence anywhere honestly degenerates to the flat prior
and says so (`is_flat`); the new prior is
Beta(k0·mu0, k0·(1-mu0)) with a stated 0.5 Jeffreys floor so an extreme
pool cannot produce an improper prior — a documented rule of the
estimator, not a silent clamp of user data; `shrunk_mean` reports each
arm's shrinkage weight, which visibly decays as its own evidence grows.
Pure, deterministic, JSON-round-trippable; the first consumer is this
backlog's own 3.4 timing bandit (its arms are seeded from the existing
proposal bandit's pooled statistics rather than flat).

**3.2 off-policy evaluation gate.** `brain/ope.py` (CLI: `brain ope
SWITCH`) is the gate the operating prompt demands before any agent —
this one or a successor — proposes flipping a capability kill-switch:
the historical approve/reject ledger is replayed through the candidate
policy with an importance-weighted estimator (Horvitz-Thompson
weights; the off-policy framing of Dudik, Langford & Li 2011), and the
estimated accept rate is PRINTED with support and coverage accounting.
Known switches have explicit candidate filters over the ledger
episode's own (kind, target, diff) fields — a reviewable table, no
guessed semantics; an unknown name lists what exists. Honesty
accounting: a deterministic candidate has weight 1 inside its support
and 0 outside, so episodes the candidate would never have proposed are
EXCLUDED and the gap is REPORTED as 1 - coverage — never silently
extrapolated; zero support (pure extrapolation) and thin support
(< 5) are explicit refusals rather than shrug-of-a-number estimates;
the module writes NOTHING anywhere (ledger byte-identity pinned by
test) and the standing note on every report says flipping the switch
stays a human file edit.

**3.3 regret-vs-best-fixed audit.** `brain/regret.py` (surfaced in
`cortex report` for the strategy bandit and in `brain calibration` for
the preset bandit): cumulative reward vs the best-fixed-arm-in-hindsight
baseline, printed every time the periodic report runs. Honesty
accounting: the flat prior's own mass is never counted as plays or
rewards; the best-fixed total is labeled an ESTIMATE (it assumes the
best arm's observed mean would have held over the whole horizon —
unplayed rounds are unobserved) and the caveat travels on every
report; a bandit with fewer than two played arms states that no policy
comparison exists (regret 0 by definition); an untouched bandit
ABSTAINS rather than reporting a meaningless zero; both input shapes
work (aggregate posteriors and explicit per-round draw logs);
deterministic, pure, nothing acts on the number.

**3.4 attention-aware suggestion timing.** `brain/timing.py` composes
the existing engines — the Thompson-sampling bandit family (HourBandit's
algorithm via NamedBandit's named arms, now over TIME BUCKETS instead
of prompt content), the rhythm engine's activity z-scores, Holt's
acceptance-rate trend, and historical surface-to-decision latency per
bucket — to rank WHEN a proposal should surface. It is also the
promised consumer of 3.1: the timing arms are seeded from the POOLED
statistics of the user's existing proposal posteriors (pooling itself
states when there is nothing to borrow and stays flat). Honesty
accounting: the output ranks buckets and may ADVISE deferring on a
falling Holt forecast — reported, never enforced; the note on every
result says it biases WHEN, not WHAT, and that proposals still go
through the ledger's approve/reject flow; nothing surfaces
automatically; deterministic under a seeded rng (the one stochastic
step, Thompson sampling, is the same one every other bandit uses);
bad inputs (hour outside [0, 24)) are refused.

**4.1 disk-backed bounded-memory search index.**
`retrieval/diskindex.py` (+ `retrieval cli disk-index / disk-search`)
indexes an arbitrary folder tree under a stated RAM ceiling via a
classic external merge sort: postings accumulate in a run buffer whose
character budget IS the ceiling (checked BEFORE each append, so the
buffer is never past it — a construction claim, not a hope), runs are
spilled to sorted temp files, `heapq.merge` k-way merges them into a
term-sorted postings JSONL, and queries load ONLY the metadata — the
searcher structurally has no postings dict (pinned by test). Scoring
reuses `indexer.tokenize`/`idf` and the Searcher's k1/b, so both
indexes answer with the same BM25. The footprint claim is MEASURED,
not asserted: the report carries /proc VmHWM before/after, the
enforced budget, `budget_respected_by_construction`, and the
process-level observation (`hwm_growth_within_ceiling`) with the
explicit note that VmHWM includes the whole interpreter — if the
number says the ceiling was breached at process level, the report
says so. Read-only walk; the only writes are the index files the
caller named plus removed spool files; no subprocess, no network;
lookup is an honest sorted-file scan built for low RAM, not latency.

## What was deliberately not done

- No training or fine-tuning (not enough data; unnecessary for the scope).
- No pip dependencies, no embeddings, no network index.
- No changes to the shipped shell's own CLI (`caelestia`, `caelestia-color`)
  or to any shipped QML beyond the two files this repository deliberately
  patches (`AiAssistant.qml`) and adds (`SettingsTools.qml`) — both left as
  unreviewed, separately-reviewable diffs for the maintainer's own pass; the
  four troubleshooting layers touch no shipped shell code at all.
- No push to upstream, no pull request, no issue filed: this branch
  is pushed to the fork for the maintainer to review — the work is
  committed (git history intact, one commit per phase, WORKLOG.md
  recording every session), never squashed, never force-pushed, and
  the maintainer's accept/reject decision stays theirs.

## Known gaps left for human review

- Doc anchors are normalized to exact GitHub slugs — every rule anchor
  resolves to a real `TROUBLESHOOTING.md` heading.
- **Live notification observation** (the notification-triage archetype
  is a PURE classifier of event records): watching notifications live
  would need the DBus surface, which now exists
  (`settings/dbus_surface.py`, quarantined, kill-switched OFF) but
  carries no notification-listening command — adding one is a
  reviewable catalog diff plus the maintainer sign-off the DBus
  proposal's own escalation demands. Until then the archetype works
  only on records the user hands it.
- **Filesystem event watching (fsbrain)**: no stdlib-legal event source
  exists on this platform — `select()` on directory fds always reports
  ready (measured), and `ctypes` (the only stdlib route to inotify(7))
  is rejected by name in ALLOWED_IMPORTS.txt. If a resident watch ever
  becomes a real requirement, the honest options are a quarantined
  ctypes inotify wrapper (a per-module allow-list exception in the
  documented quarantine pattern) or a short-lived watcher subprocess
  per §2 — both deliberate design decisions, not implementation
  details, and neither is needed by anything shipped today.
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
