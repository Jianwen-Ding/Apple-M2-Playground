# Direct return-arrival observations

36 cases with all three valid targets active: first positions 0,1,5,8,16,24,
winners A/B/C, seeds 103/809. The last plane of the parent three-target table
is now r0l before the first pop, replacing the same-sized post-pop r1 snapshot.
Every target address and total program size stays fixed.

Each record retains exact original/control bytes, initialized table, complete
surrogate gates, raw hardware readback, source hashes, diagnostics and recovery.
`source-before-model/` also archives the initial and refined depth-probe sources
for provenance across future model correction. All originally inactive lanes
write zero before any pop; the legacy model predicts no writes.

`make verify-ret-mask-state` checks these 36 cases and the adjacent 21-case
depth matrix with independent membership/counter oracles. It uses no GPU.
See the [finding](../../novel-results/2026-10-20-ret-mask-state/README.md).
