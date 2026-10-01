# MODELS — the optional generative layer's model guidance, stated honestly

Guidance for a maintainer or user deciding whether — and what — to serve
for `assistant.generative` (Layer 3). This document changes no code: the
layer's transport (`client.py`), its orchestrator (`rag.py`), and its
default model string are unchanged. It only describes what this project
will and will not recommend, and why.

## The constraint

From issue #120's thread and the layer's own design:

- **On-device and non-resource-hungry.** The model runs on the user's own
  machine, next to the shell.
- **Served by the user's local Ollama on loopback.** The assistant speaks
  only to `http://127.0.0.1:11434` (the port is configurable via
  `CAELESTIA_ASSISTANT_OLLAMA_URL`); any non-loopback host is rejected
  before a connection is opened. The only network activity is a single TCP
  connect (availability probe) and a single POST per enabled invocation —
  no retries, no pools, no background work.
- **The assistant stays OFF by default and downloads nothing.** Layer 3
  activates only when `--generative` is passed AND a loopback Ollama
  answers; with zero retrieval hits the model is not contacted at all. The
  assistant contains no download code of any kind and never fetches a
  model, weights, or anything else from the network.

## What this project does NOT recommend: an 8B-class chat model

This document previously recommended an 8B-scale open-weight instruct
family served quantized. That recommendation is **withdrawn**, on the
project's own evidence:

- The README states the honest hardware target in one line: this
  assistant is built to run "on hardware that would struggle to load an
  8B model." Recommending an 8B-scale model for that hardware was a
  self-contradiction between two pages of the same repository, and the
  contradiction is resolved in favor of the hardware statement — the
  assistant's whole reason to exist is the machines LLM tooling ignores.
- Even quantized to 4-bit class, an 8B model is on the order of ~5-6 GB
  of resident memory (a rule-of-thumb approximation, not a measured
  number). That is not "next to the desktop session" on the machines this
  project targets; it IS the desktop session's entire memory budget.
- The layer's job in the fallback path is suggestion formatting over
  retrieved excerpts — work a sub-1B model can attempt, and work the
  deterministic layers already do better when they can do it at all.
- The earlier recommendation also rested on a family that was not in the
  Ollama model library at all: the library page for `apertus` returned
  **404** when checked live (2026-09-23), so the old page already had to
  recommend "the family and the size class, not a pull command." A
  recommendation the user cannot act on from the library is not a
  recommendation; it is a wish.

What remains true and unchanged: if a user *chooses* to serve an 8B-class
model on hardware that fits it, the layer works — the transport does not
care what the model is. The assistant will not recommend that choice,
because the recommendation would contradict the hardware this project is
for.

## What this project CAN recommend: sub-1B, reranker role only

The one model class that fits the constraint is sub-1B. The one role
where a model adds something the deterministic layers cannot is the
**reranker role**: taking the router's own candidate list and proposing
an order (never a new answer, never free text — see the MODEL_SUGGESTED
contract in `assistant/generative/reranker.py`).

Candidates, verified against the Ollama model library (pages fetched
live 2026-09-30; download sizes are the library's own numbers):

| Model (Ollama tag) | Download | License | Library page |
| --- | --- | --- | --- |
| `smollm2:135m` | 271 MB | Apache 2.0 | ollama.com/library/smollm2 (HuggingFaceTB SmolLM2) |
| `smollm2:360m` | 726 MB | Apache 2.0 | ollama.com/library/smollm2 (HuggingFaceTB SmolLM2) |
| `qwen2.5:0.5b` | 398 MB | Apache 2.0 (the library page states all Qwen2.5 models except the 3B and 72B are Apache 2.0) | ollama.com/library/qwen2.5 |

All three are IN the Ollama model library — unlike the apertus family
the withdrawn recommendation above pointed at, which had no listing at
all. Serving one is a user-side step (pulling the tag with your own
local Ollama, or a local Modelfile, at the user's choice); the
assistant downloads nothing, ever, and defaults to `llama3` for upstream
alignment until told otherwise.

## How to point the layer at a model (existing surface, no code changed)

- CLI flag: `--model <name>` on `python3 -m assistant.generative` (e.g.
  `python3 -m assistant.generative "problem" --generative --model <name>`).
- Environment variable: `CAELESTIA_ASSISTANT_OLLAMA_MODEL` (used when
  `--model` is not passed).
- The server URL: `CAELESTIA_ASSISTANT_OLLAMA_URL` — loopback-only; any
  non-loopback value is rejected before a connection is opened. There is
  no CLI flag for the URL.
- Precedence: explicit `--model` > `CAELESTIA_ASSISTANT_OLLAMA_MODEL` >
  default `llama3` (this is `client.resolve_model`, unchanged).

The default `llama3` string is kept for alignment with upstream
`aiconfig.hpp` (`defaultOllamaModel`, aiconfig.hpp:22; `ollamaModel`,
aiconfig.hpp:16) — upstream ships that default, so the shell's own config
and this layer agree out of the box. The alignment is stated here rather
than defended: `llama3` is itself an 8B-class model, which is exactly why
this page no longer recommends the class. On constrained hardware the
honest options are a sub-1B model or the layer staying off — which is the
default, and on the target hardware, the right answer.

## Not bundled, downloaded separately — the maintainer's own words

From issue #120 (https://github.com/ladybug-me/caelestia-kde/issues/120):

> we can't ship the model bundled with the shell, it'll have to be
> downloaded from the ui. easier to handle things like updates too if we
> don't have to manually watch for bumped versions
> — 0xSolanaceae (COLLABORATOR, 2026-09-22)

> gonna publish that on GitHub instead cuz it will be ofc greater than
> 500mbs
> — 0x0nYx (2026-09-22)

The direction is consistent: the model is a separate, user-downloaded
asset, never a bundled repository file, and updates flow through that
separate channel rather than through the shell's repository.

## Explicit non-goals

**No training. No fine-tuning. No distillation. No dataset collection. No
model hosting. No network beyond the single loopback Ollama call.** The
assistant is a client over whatever model the user already serves
locally; it never creates, adapts, or improves a model, and it never
collects data for one. If the maintainer later ships the model-download UI
that the #120 thread describes, this layer needs zero changes: the user
selects the model in the UI, and the assistant's `--model` /
`CAELESTIA_ASSISTANT_OLLAMA_MODEL` surface simply points at it.
