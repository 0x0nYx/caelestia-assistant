# MODELS — which model to serve locally for the optional generative layer

Guidance for a maintainer or user deciding which model to serve for
`assistant.generative` (Layer 3). This document changes no code: the layer's
transport (`client.py`), its orchestrator (`rag.py`), and its default model
string are unchanged. It only recommends — and it recommends a family and a
size class, never a download that the assistant itself would perform.

## The constraint

From issue #120's thread and the layer's own design:

- **On-device and non-resource-hungry.** The model runs on the user's own
  machine, next to the shell, and must not demand workstation-class
  hardware.
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

## The recommendation: a small open-weight 8B-scale instruct model, quantized

For a RAG client that formats retrieved excerpts into a suggestion, the
model needs instruction following, not frontier reasoning. A small
open-weight instruct-class model at roughly the 8B scale, served quantized
(4-bit-class GGUF), fits the constraint — and is never a model anyone would
need to pretrain or otherwise create: it already exists, with open weights,
and the assistant only ever does inference over it.

Concretely, this document recommends the **Apertus 8B family** — the model
family the maintainer's collaborator pointed issue #120 itself at
(0xSolanaceae, COLLABORATOR, 2026-09-22: "i'd like to explore using this
family of models for the assistant: https://www.apertus-ai.org/").

Verified facts about Apertus (source: apertus-ai.org, fetched live
2026-09-23):

- "Fully Open Foundation Model for Sovereign AI".
- Developed by the Swiss AI Initiative as a collaboration between EPFL,
  ETH Zurich and CSCS.
- Open weights, open data, open science.
- Ships at 8B and 70B parameter scales; **the 8B scale is the on-device
  fit** (70B is not).
- Multilingual ("multilingual from day one, trained on 1000+ languages").
- Apertus 1.5 (2026-07-24 post) added multimodal input, reasoning, longer
  context and better instruction following.

## Why quantized

A rule of thumb, clearly labeled as an approximation and NOT a measured
number on any particular machine: an 8B-parameter model typically needs on
the order of ~5-6 GB of memory at 4-bit-class quantization, instead of
~16 GB at 16-bit precision. On a typical laptop, that is the difference
between "fits next to the desktop session" and "does not fit". No
benchmark scores are claimed here — for this layer's suggestion-formatting
workload the relevant property is memory fit, not leaderboard position.

## What is NOT true / not available (honesty section)

- As of 2026-09-23 there is **no `apertus` listing in the Ollama model
  library**: `https://ollama.com/library/apertus` returns **404** (checked
  live). This document therefore recommends the family and the size
  class, **not a pull command**. To
  serve an Apertus build, the user points their own local Ollama at a
  quantized GGUF via a local Modelfile or equivalent — a user-side,
  user-controlled step that this document deliberately does not script,
  because the assistant itself never fetches anything.
- The layer's own default model string stays **`llama3`** — unchanged, and
  aligned with upstream `aiconfig.hpp`'s
  `defaultOllamaModel` (aiconfig.hpp:22) and `ollamaModel`
  (aiconfig.hpp:16) defaults. `llama3` is itself an 8B-class instruct
  model, so the default already satisfies the size constraint; nothing in
  this guidance requires changing it.
- This document adds guidance only. The transport, the orchestrator, the
  off-by-default gate, and the output sanitizer are untouched.

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

## Not bundled, downloaded separately — the maintainer's own words

From issue #120 (https://github.com/ladybug-me/caelestia-kde/issues/120):

> we can't ship the model bundled with the shell, it'll have to be
> downloaded from the ui. easier to handle things like updates too if we
> don't have to manually watch for bumped versions
> — 0xSolanaceae (COLLABORATOR, 2026-09-22)

> gonna publish that on GitHub instead cuz it will be ofc greater than
> 500mbs
> — 0x0nYx (2026-09-22)

The direction is consistent: the model is a separate, user-downloaded asset
(expected to be published on GitHub, being greater than 500 MB), never a
bundled repository file, and updates flow through that separate channel
rather than through the shell's repository.

## Explicit non-goals

**No training. No fine-tuning. No distillation. No dataset collection. No
model hosting. No network beyond the single loopback Ollama call.** The
assistant is a retrieval-augmented-generation client over whatever model
the user already serves locally; it never creates, adapts, or improves a
model, and it never collects data for one. If the maintainer later ships
the model-download UI that the #120 thread describes, this layer needs
zero changes: the user selects the model in the UI, and the assistant's
`--model` / `CAELESTIA_ASSISTANT_OLLAMA_MODEL` surface simply points at it.
