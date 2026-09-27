# The upstream case: a classical layer beats a bundled small LLM here

This document is the repo's explicit position on a question issue #120
opened and never closed: should the caelestia shell's natural-language
assistant be built on a downloaded small LLM, or on a deterministic,
on-device, classical layer? The position of this repository is the
latter, for a config-editing use case on low-end hardware. The quotes
below are verbatim from the captured issue thread in
`assistant/retrieval/corpus/ISS-120.md` (citation-pinned; read-only).

## What the thread itself records

The size problem was stated by this repo's own contributor in the
thread:

> **0x0nYx** (NONE, 2026-09-22 15:03): "also you have more than 150mbs
> sized assets alone, rather than code, when building an llm, atleast
> 200-300M parameters are required, 100M for learning English alone
> btw, we can just add a normal translation layer afterwards, no need
> to worry any that, but the size of the model will increase with its
> parameters...."

> **0x0nYx** (NONE, 2026-09-22 17:24): "the model download is another
> overhead for non technical users.... gonna publish that on GitHub
> instead cuz it will be ofc greater than 500mbs."

The collaborator's direction was a model family (Apertus) and a
download, never a bundle — and the work was explicitly backlogged:

> **0xSolanaceae** (COLLABORATOR, 2026-09-22 15:29): "i'd like to
> explore using this family of models for the assistant:
> https://www.apertus-ai.org/ ... feel free to throw in a pr."

> **0xSolanaceae** (COLLABORATOR, 2026-09-22 16:38): "also we can't
> ship the model bundled with the shell, it'll have to be downloaded
> from the ui."

> **0xSolanaceae** (COLLABORATOR, 2026-09-22 17:46): "now you see why
> it hasn't been implemented yet -- this has fallen to the backlog bc
> of all the more important features and bugfixes we need to ship
> first"

So the thread's own facts are: a 200-500 MB model asset, a mandatory
download step for non-technical users, and no settled model choice.
The thread is OPEN; nothing below re-decides it — this document only
records why this repo built the alternative first.

## The argument

**1. The task is narrow and enumerable; a small model is a loose fit.**
Config editing is not open-ended English. It is: map a request onto the
shell's registry of tools, validate ranges, preview, apply with undo.
The thread's original proposal said exactly that ("convert it into
structured configuration changes, and apply them through Caelestia's
existing configuration system"). A frozen grammar plus a 277-tool
registry with per-tool citations solves the whole shape of that problem
deterministically — same input, same plan, byte-identical — while a
200-300M-parameter model buys fluency this task does not need and
hallucination risk this task cannot afford.

**2. Grounding is not optional when the output writes config.** Every
tool call this repo produces carries its C++ declaration citation, its
shipped control, and a live QML reader; every plan is validated against
the registry before preview; out-of-range values are rejected, never
clamped. A small model interpolating English cannot make those
guarantees; it can only be prompted to pretend to. The failure mode
matters: a plausible-sounding wrong key silently unsets a user's
setting.

**3. Low-end hardware is the stated audience.** A 200-500 MB download
plus resident inference RAM is a real cost on the machines a dots repo
targets. The classical layer is a one-shot CLI process: no daemon, no
resident model, idle RSS ~0. The same request "make my bar thinner"
that would wake a quantized model is answered by a regex-compositional
grammar in well under a second, offline, on any CPU.

**4. A partial-English small model is a language tax.** The thread
notes ~100M parameters "for learning English alone". A small
multilingual model spends most of its budget being a mediocre language
model and the rest being a mediocre config parser. The grammar spends
its whole budget on the config domain — and unknown phrasings fall
through to honest AMBIGUOUS/ABSTAIN verdicts instead of confident
wrong ones.

**5. Review safety composes with determinism.** The safety contract
(dry-run -> plan -> consent -> backup -> bounded undo) needs a plan a
human can audit. A deterministic planner produces the same plan every
time for the same request, so a reviewed request stays reviewed. A
sampled model produces a different plan next Tuesday.

**6. The LLM path stays available where it belongs.** This repo keeps
the loopback-only optional Ollama client (off by default, hard-rejects
non-loopback hosts) and the opt-in user-keyed cloud sidebar whose every
state-changing call routes through the local gate. The classical layer
is not anti-LLM; it is the layer that makes an LLM optional instead of
load-bearing.

## The honest scoreboard

| | bundled/downloaded small LLM | this repo's classical layer |
| --- | --- | --- |
| Asset size | 200-500+ MB download (thread: "greater than 500mbs") | ~0 (stdlib-only code) |
| Resident RAM | model-resident inference | ~0 (one-shot CLI) |
| Same input, same plan | no (sampling) | yes (deterministic, tested) |
| Wrong-answer shape | fluent, confident | AMBIGUOUS / ABSTAIN with evidence |
| Grounding | prompt-hoped | citations enforced by lint + tests |
| Offline | only after download | always |
| Network | model download + runtime API | none by default |

## Sources

- `assistant/retrieval/corpus/ISS-120.md` — the citation-pinned capture
  of issue #120 (state OPEN, backlogged per 2026-09-22); all quotes
  above are verbatim from it.
- `CHANGELOG.md` [0.1.0] — the shipped layer this document argues for.
- `docs/PR_SURFACE_PLAN.md` — what is proposed to go upstream first,
  given the thread's backlog state.
