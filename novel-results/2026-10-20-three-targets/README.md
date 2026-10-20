# Call and return rules hold with three active destination addresses

Observed on M2 Max G14C B1, direct DRM, compute, AC power, 2026-10-20.
**72 variants / 216 dispatches, zero faults, every exact recovery control passed.**
The current simulator predicts all results before hardware execution.

Three distinct decoded landing blocks A/B/C are represented in active lanes
in every case. Seed scattered participation; force first, first+2 and lane 31
active, give them different destinations, and leave a hole at first+1. Use
first-active positions 0,1,5,8,16,24, rotate the first lane's destination through
A/B/C, and use two fixed seeds (103/809), for both call and return. Other
active lanes can share any of the three addresses. Inactive lane 0 disagrees
with the winner where it is masked.

All 72 full readbacks match independent scalar oracles:

- The **lowest active lane** chooses the destination for both operations;
  address order and the other two active alternatives do not change it.
- A call enters with only the issue-active lanes matching that destination.
  All issue-active lanes receive the link, including non-entering lanes;
  inactive lanes keep r1. One pop reactivates everyone in the tested masks.
- A return's first pop exposes previously inactive lanes, its second exposes
  all lanes, and r1 remains unchanged. This records post-pop membership and
  preservation; it does not establish the unobserved state before the first
  pop or resolve the separate stop/return counterexamples.
- No alternate landing or fallback marker appears. All input planes, unused
  words, main output, guards and patterned tails remain exact.

The exact original program and table pass `agx_run` with the measured model
before hardware submission. Three uniform-operand substitutions and three
known direct-jump substitutions additionally validate all landing paths. Call
surrogates filter participation before issue and use a synthetic link for jump
controls; their distinct post-pop r1 values are checked explicitly. Return
jump controls have the original mask and no artificial return-depth change.
Known-op jump-A controls bracket every hardware variant.

This extends the [two-target/scattered results](../2026-10-20-sparse-control/README.md),
without a new simulator change. The register-source/link alias remains covered
separately by [`call r1`](../2026-10-20-call-r1/README.md). Four or more targets,
nested divergence and the state before return reconvergence remain open.

```sh
python3 -B scripts/probe_three_targets.py --kind call --first 1 --winner C
python3 -B scripts/probe_three_targets.py --kind ret --first 1 --winner C --hardware
make verify-three-targets
```

All addresses stay inside completely decoded programs, with no loop or barrier.
The watchdog retains exact programs, tables, source hashes, kernel/firmware,
memory and recovery state. [Evidence](../../results/2026-10-20-three-targets/README.md).
