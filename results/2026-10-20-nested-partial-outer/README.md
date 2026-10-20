# Partial original outer-call evidence

144 records: two outer forms, prefix lengths 1/5/16/24, winners A/B/C, seeds
17/257, inner pop counts 0/1/2. Every candidate has exact no-call controls
before/after: 432 dispatches, zero faults. Exact code/input/readbacks, hashes,
all-target gates, decoded boundaries, firmware samples and diagnostic/recovery
metadata are preserved. Initial cases for all three pop counts were inspected.

The 528-word table extends nested early-return traces with original outer-mask
input at plane 15 and 16 guards. All saved r29 values are initialized to a
valid newly computed outer link before masking. Original excluded r1 is only
observed as payload before initialized r29 restoration, never consumed as a
return target. Function/inner-link addresses stay fixed; direct outer branch
and link are recomputed after setup insertion.

`make verify-nested-partial-outer` independently checks lane sets, original r1
payloads, saved/restored links, pre-pop behavior, every guard and exact code
provenance, then replays the original behavior offline. See the
[finding](../../novel-results/2026-10-20-nested-partial-outer/README.md).
