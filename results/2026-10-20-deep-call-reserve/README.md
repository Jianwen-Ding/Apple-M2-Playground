# Deep balanced-call reserve evidence

192 compressed records: depth 3 with four static call patterns, depths 4/8
with both alternating patterns; four suffix starts, three leaf winners, two
seeds. Last call is always a three-way divergent register call. Each has exact
no-call controls before/after: 576 dispatches, zero faults. Initial cases at
each depth were inspected separately. Exact programs/inputs/readbacks, hashes,
all-target model gates, boundaries, firmware and diagnostic/recovery data are
preserved unchanged.

Table planes: leaf target input, original mask input, prefix marker; eight
planes per call (entry link/counter/identity, continuation before pop counter,
pop-1 marker, pop-2 marker/link/restored counter); caller-mask marker, full-group
marker and final r1 after original-IF pop, then 16 guards. Every frame's source
lane 0 is initialized and originally excluded; counter reads are immediate
shuffles masked to 16 bits. Original excluded saved-link registers are seeded
with a valid main continuation before divergence. Bounded drain pops occur
after diagnostics. `make verify-deep-call-reserve` independently checks every
word and link formula and replays the original behavior offline. See the
[finding](../../novel-results/2026-10-20-deep-call-reserve/README.md).
