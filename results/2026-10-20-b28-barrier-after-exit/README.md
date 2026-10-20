# B28: the threadgroup barrier after SIMD groups or lanes have ended (2026-10-20)

Blocker B28 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: the threadgroup barrier (0x68) does
not wait for SIMD groups or lanes that have ended. All four probes completed normally (~8 us), so PTX clusters run as
one threadgroup, and `bar.sync` after an early `ret` of whole warps, are safe.** Step 5 (recovery from a hung barrier)
was not needed. 0 faults, hang budget unchanged (3/30).

`b28.py`: lanes that pass the barrier(s) output 0x5e5e0000 | gid, skipping groups output 0xaaaa0000 | gid, stopped
lanes output nothing. Each ran in `agx_run` first with the same outcome.

| Probe | Threadgroup | What ends early | Barrier side | Result on the GPU |
| --- | --- | --- | --- | --- |
| p1 | 64 threads (2 groups) | group 1 jumps over the barrier section (`jmp_exec_none`) to `stop` | group 0: barrier, sentinel | completes, 32 lanes passed, 32 skipped, 8.0 us |
| p2 | 64 threads | group 1 after one common barrier | group 0: two barriers | completes, 8.4 us |
| p3 | 1,024 threads (32 groups) | odd groups skip | even groups: barrier | completes, 512 passed, 8.5 us |
| p4 | 32 threads (1 group) | lanes 16-31 `stop` under a partial mask | lanes 0-15: barrier | completes, lanes 0-15 passed, 16-31 stored nothing, 7.8 us |

## Largest threadgroup memory of one threadgroup (`tg64k.py`)

One 1,024-thread threadgroup declaring 65,536 bytes (Shared word size field 0 = 64 KiB): thread i stores at bytes
64i and 64i + 60 (up to byte 65,532), barrier, then reads both words of thread i + 1. **0 wrong of 1,024** (also in
`agx_run`), 12.3 us. So one threadgroup can use the whole 64 KiB, not just Mesa's 32 KiB; C x per-CTA shared memory
for clusters is bounded by 64 KiB.
