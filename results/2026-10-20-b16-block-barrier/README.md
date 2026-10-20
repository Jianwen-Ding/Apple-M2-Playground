# B16: what the 0x78 block barrier orders, partial blocks and divergence (2026-10-20)

Blocker B16 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: `agx.block_barrier` can be lowered to
0x78 (`7809`) alone.** It orders memory within its aligned 4-SIMD-group block, it completes when the workgroup has
fewer than 4 groups, and it completes in divergent control flow.

## Ordering (from existing findings)

- `novel-results/2026-10-20-barrier-bits`: in the message-passing stress loop **with no fence before the barrier**,
  `7809` gives 0 mismatches for readers inside a 4-group block, in threadgroup and in device memory; only readers of
  another block (groups 3 and 7) fail. So 0x78 orders memory between the SIMD groups of its block like 0x68, and the
  extra threadgroup-memory fence is not needed for that.
- `novel-results/2026-10-18-tg-litmus`: threadgroup memory between two SIMD groups is in program order even with no
  fence at all.

## Completion (`b16.py`, new)

Each program was checked in `agx_run` with `6800` in place of `7809` (identical layout; the simulator cannot decode
`7809`), then run on the GPU with `7809`. Lanes past the barrier output 0x5e5e0000 | gid. 0 faults.

| Case | Threadgroup | Who executes 0x78 | Lanes past it | Firmware time |
| --- | --- | --- | --- | --- |
| q1 | 64 threads (2 groups: half a block) | all | 64 / 64 | 7.3 us |
| q2 | 96 threads (3 groups) | all | 96 / 96 | 7.0 us |
| q3 | 128 threads | groups 0-1 in the `if`, groups 2-3 in the `else` (two instruction addresses) | 128 / 128 | 7.8 us |
| q4 | 128 threads | odd lanes only (partial mask in every group) | 64 / 64 (even lanes skipped) | 7.7 us |

So a partial block does not wait for missing groups, and the barrier is safe from different code addresses and under a
partial execution mask (as long as every group of the block reaches one).
