# Nested early-return evidence

Twenty-four compressed records: direct/indirect outer calls, three inner
winning targets, seeds 17/257, zero/one inner pop. Every candidate has exact
no-call controls before and after: 72 dispatches, zero faults. Original code,
input/readbacks, source/harness hashes, model gates, instruction boundaries,
firmware samples and watchdog/kernel/memory/recovery data are retained.

The nested-divergent trace adds plane 14 for a direct main-landing pre-pop
r0l snapshot; plane 13 remains the main pop-1/fallback diagnostic. Same-size
wait replacements remove inner pops, and the added checkpoint consumes only
STOP padding so no function, return target or link moves. The table has 496
words including guards. All saved outer links are initialized by the original
full-group call before inner divergence.

`make verify-nested-early-return` reconstructs bytes, resolves source hashes,
checks link formulas and independently verifies every word, including mixed
final inner/outer r1 values and pre-pop reactivation. See the
[finding](../../novel-results/2026-10-20-nested-early-return/README.md).
