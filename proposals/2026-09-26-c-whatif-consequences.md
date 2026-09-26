# Tier C Proposal 4 — What-if consequence-graph mode (HTN + AC-3 before multi-tool execution)

**Status: PROPOSAL ONLY — no implementation without explicit sign-off.**
The gap it closes: presets and batch proposals apply 3-5 tools at once,
but the only pre-apply artifact is the flat plan list. A what-if mode
projects CONSEQUENCES (what else changes because a tool changed, what
constraints would be violated) before the user consents.

## Approach

Two existing engines compose; one new pure module
`assistant/settings/consequences.py`:

1. **Interaction graph**: a small, hand-curated, citation-backed table of
   KNOWN cross-key interactions in the shell's own code, e.g.
   `appearance.transparency.enabled=false ⇒ blur behaves differently`
   (AppearancePage.qml:132-136 — the same fact the parser's transparency
   dead-end already cites), `bar.scale very low ⇒ dock icon bounds`
   (BarWrapper.qml:24-26 clamp). Each edge: {affects, direction, citation,
   confidence}. NOT a general model — a cited-edge list the registry
   discipline already governs (uncited edges are lint errors).
2. **Projection**: `consequences.project(ops)` — take a candidate op list,
   walk the interaction graph transitively (bounded, cycle-safe), and
   return (a) derived-effect nodes the user did NOT ask for, each with
   its citation, (b) the op list annotated with each op's downstream
   count.
3. **Constraint check**: `optimize.check_conflicts` (AC-3, already
   shipped) runs over the candidate list + derived nodes; UNSAT is
   reported with the conflicting domains — the existing behavior,
   extended to see induced values.
4. **The what-if surface**: `settings what-if "compact" --for gaming` —
   renders the projected graph as text (nodes, edges with citations,
   conflict verdict) and a REVERSIBILITY summary (which ops have undo
   records, which don't — feeding the A3 undo-log machinery). The agent
   layer can render the same dict behind `--simulate` before any node
   runs — the consent card then shows consequences, not just actions.

## Footprint (§2.6)

The interaction table is static data (target: ≤ 30 edges, ~5 KB). The
projection is a BFS over ≤ 30 edges × ≤ 10 ops: microseconds, zero
steady-state memory. No new imports (collections.deque, already
allow-listed).

## Safety-contract implications

- Purely read-only: the what-if mode is a VIEW. It never writes, never
  applies, and cannot be reached from an NL request that would apply —
  the parser/planner/applier spine is untouched; the new module only
  reads op lists.
- The honesty rule it must obey: a cited-edge list can be WRONG if the
  upstream code changes. Mitigation: every edge carries its citation;
  the existing all-cited-lines-re-verification test pattern (registry)
  extends to the edge table — an edge whose cited line no longer matches
  its claimed content is a test failure, not a silent stale edge.
- Doctrinal note: this is NOT "fake open-endedness" (§4): the
  consequence universe is exactly the cited-edge table — bounded,
  auditable, growable by reviewed diffs.

## Verification plan

1. Edge-table lint: 100% of edges resolve to real cited lines
   (same harness as the registry's citation re-verification).
2. Projection tests: transitive effects, cycle safety, bounded output on
   adversarial op lists (10 ops, dense edges).
3. AC-3 integration: a candidate list that is independently valid but
   jointly UNSAT through derived nodes is refused with reasons.
4. Snapshot: the rendered what-if for the two shipped presets is pinned
   byte-for-byte (it changes only when the edge table changes, which is
   a reviewed diff).
5. Agent seam: `--simulate` output for a mixed goal includes the
   consequences dict, and consent cards carry the reversibility summary.
