# Lowest-active call/return selection and call links also hold with inactive holes

**Simulator integration, later 2026-10-20:** the measured model now replays this full corpus exactly; current probes require actual-program equality. [Validation, original source provenance and remaining limits](../../results/2026-10-20-control-simulator/README.md). Earlier gate descriptions below record what was known before hardware.

Confirmed in this matrix on M2 Max G14C B1, direct DRM, compute, AC power,
2026-10-20. **248 variants / 744 dispatches including exact controls, zero
faults, every recovery passed.** This extends the contiguous-suffix findings
for [return selection](../2026-10-20-ret-winner/README.md) and
[call selection/link writes](../2026-10-20-call-winner/README.md).

Keep every program byte fixed and change only initialized participation bits.
For each first-active lane k=1..31, both target assignments and two fixed mask
seeds, run both a return probe and a call probe with a post-pop link snapshot.
Keep all lanes below k inactive, force lane k and (where distinct) lane 31
active, and force a hole at k+1 where possible. Other higher bits are seeded
random values. Positions 30/31 cannot have an interior hole and serve as edge
controls; short suffixes can repeat the same masks across seeds.

All observed traces match the independent hypotheses:

- **Return:** the lowest active lane supplies the selected target. Every
  previously inactive lane, including holes above k, writes the first landing
  marker after pop 1; all lanes write after pop 2.
- **Call:** only the matching active lane enters the selected callee, then a
  single pop reactivates all lanes. Every lane active at issue receives the
  implicit two-byte call link, including non-entering lanes. All inactive
  holes retain the initialized `0xf1f10000` r1 sentinel.

There is no prefix-only behavior or stale inactive-lane-0 winner in this
matrix. The call-link write follows the original participation bitmap rather
than a contiguous index interval. These are two valid candidate addresses,
one physical SIMD group and one transfer; more addresses, nested divergent
calls, full return-state mechanics and invalid-target behavior are not covered.

For every sparse table, rerun both uniform and forced-jump surrogate programs
with that **exact** table and independent full-buffer oracles. The prefix-only
gates are not reused as proof for the sparse inputs. Actual simulator rejection
is retained in 244 records; four single-active returns simulate directly.
No model guard was removed. Both known-operation controls and all trace/main
words, input planes, guards and tails match their independent checkers.
The simulator extension remains a separate follow-up after recording these
hardware results.

```sh
python3 -B scripts/probe_sparse_control.py --kind ret --first 1 --seed 211
python3 -B scripts/probe_sparse_control.py --kind call --first 1 --seed 211 --hardware
make verify-sparse-control
```

The full matrix uses kinds ret/call, k=1..31, winner A/B and seeds 211/701.
Records refuse overwrite. [Retained evidence](../../results/2026-10-20-sparse-control/README.md).
