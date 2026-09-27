# assistant/diagnostics — deterministic troubleshooting

Layer 1: reads pasted text/logs, matches them against the cited rule
sets in `rules.d/`, and prints a plan of INERT suggestions
(`SUGGESTED_NOT_EXECUTED:` strings with risk tiers — nothing ever
runs). `python3 -m assistant.hub selfcheck` validates the rule
schema, the risk tiers, the no-executor import policy (AST lint over
the whole tree), and the settings lint rule table. The layer also
hosts the read-only telemetry probes (`telemetry.py`: /proc + /sys
file reads, fixture-injectable paths) and, since exponential-build-3,
the Rete forward-chaining and Dung argumentation engines over matched
rules (`rete.py`, `argumentation.py`).

## Signed rule packs (`rulepack.py`)

The community rule-pack format: a manifest (id, rulesets, rule count,
`payload_sha256` over the canonical serialization — sorted keys, no
whitespace, ASCII-escaped) plus a payload of verbatim rules.d
documents. Signing happens OUTSIDE (minisign/sq/gpg over the pack
file — the assistant does no cryptography), and import verifies what
it CAN verify honestly: payload-hash INTEGRITY (post-manifest edits
refuse with both hashes named) and SAFETY (every rule passes the same
structural + forbidden-key gates the built-ins pass; a pack imports
whole or not at all). Imported packs are REVIEW DATA in the brain
state, not live rules — `render` prints a rules.d-ready document and
placing it stays a human action. Surface: `caelestia-assist rulepack
export|import|list|render|rules-d|forget`.
