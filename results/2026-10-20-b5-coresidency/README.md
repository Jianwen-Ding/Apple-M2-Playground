# B5 and B30: how many workgroups of one dispatch are co-resident, and what spinners do to the rest (2026-10-20)

Blockers B5 and B30 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: far fewer than the per-core
residency limit times 38.** With the dispatcher's uneven placement, co-residency of a whole grid was reliable up to
about 12-15 workgroups per core; above that some workgroups start only after others **exit**, so a software grid
barrier (or a spinner waiting for a later workgroup) deadlocks.

## Probe (`b5.py`)

W SIMD groups (in workgroups of 32 or 128 threads). Lane 0 of each SIMD group atomically adds 1 to a counter, then
runs exactly N = 5,000 trips that read the counter with a returning atomic add of 0 (as ZLUDA's TMEM pool spins) and
records the first trip on which it reached W (0xffffffff = never). The loop never exits early, so nothing can hang.
Every program ran in `agx_run` first. 0 faults. 64 register halves declared (the kernel uses r0-r29).

## Results (each row: one GPU run; "saw W" = SIMD groups that saw the counter reach W)

| Threads / workgroup | SIMD groups W (workgroups) | Per core (of 38) | Runs: saw W / W |
| --- | --- | --- | --- |
| 32 | 64 ... 576 (11 sizes) | <= 15.2 | **all W, every run** (5 runs each at 384, 512, 576), max trip 0-4 |
| 32 | 608 | 16 | 608, 608, 306 |
| 32 | 640 | 16.8 | 378, 640, 640 |
| 32 | 704 | 18.5 | 704, 536, 83, 205 |
| 32 | 768 | 20.2 | 198, 212, 211, 768 |
| 32 | 896 / 1,000 | 23.6 / 26.3 | 270, 95, 101 / 98 |
| 128 | 576, 1,024, 1,520, 1,672, 1,824 (144 ... 456 workgroups) | <= 12 workgroups (48 groups) | **all W, 3 runs each** |
| 128 | 1,976 (494 workgroups) | 13 workgroups (52 groups = the register limit) | 516, 516, 516 |

When co-residency fails, the late SIMD groups see W only at trips ~4,000-5,000: they started when earlier ones
finished. Per-core *peak* residency is higher (about 55 workgroups / 96 SIMD groups,
`novel-results/2026-10-18-occupancy`), but a grid is not spread evenly enough to reach it everywhere.

**Conservative rule for `cudaLaunchCooperativeKernel` / `grid.sync()` that fits both measured shapes:**
W_workgroups <= 38 x min(15, floor(S / g) - 1), where S = resident SIMD groups per core from the register count
(min(96, 2 floor(3328 / (2 H)))) and g = SIMD groups per workgroup. (32 threads, 64 halves: 570; 128 threads, 64
halves: 456.) Other register counts and threadgroup-memory sizes are not measured.

## B30 (spinning threadgroups)

The same data answers B30's probes 2-3: once spinners occupy the co-resident slots, a workgroup that is not resident
starts only after a spinner exits, so a setter launched last cannot release spinners that never give up. Spinning with
a device atomic on every iteration (as ZLUDA's TMEM pool does) does not change this. Probe 1 (two workgroups) is the
W = 64 case: always fine. **ZLUDA must bound the TMEM-using CTAs in flight to the co-resident count above** (or split
the grid), rather than spin.

## Side finding: an under-declared register count corrupts silently

The first runs declared 32 register halves for a kernel using 60. With more than about two SIMD groups per core,
groups overwrote each other's registers: the "add 0" became an add of garbage and recorded values were wrong, with
no fault and a normal completion. The backend's declared GPR count must cover every register it touches.
