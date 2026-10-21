# B18: the lane-offset fmadd forms the compiler emits, recorded and timed (2026-10-21)

Blocker B18 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM, battery power (timings are
in cycles from an in-dispatch reference, so the clock state cancels). 0 faults; hang budget unchanged.

## Recorded

`coverage.py record --area fmadd_lane_b18,fmadd_lane_b18_masked`: 28 of the 34 catalog forms recorded deterministic
(k = 1..15 in the default 16-lane mode for fmadd32 and fmadd16, fmadd16 in 4-lane segments with k = 1, partial masks);
**`suite_check`: fmadd_lane_b18 20 / 20, fmadd_lane_b18_masked 8 / 8 exact** (plus the earlier fmadd_lane 16 / 16 and
fmadd_lane_masked 8 / 8). 6 names coincide with the earlier `fmadd_lane` area's.

The other **6 forms** were refused by agx_run's gate, because the simulator does not model them: the segment modes with
k >= 2, and fmadd32 in any segment mode (a segment's first lanes read outside it). They ran through
`probe_variants.py` instead (`b18_variants.py`: the surrogate is the default-mode k = 1 form, so the whole program was
checked in agx_run and only the k / mode fields differ; lane i loads A = i + 1, then `fmadd_lane(A, 1.0, 0)`), 2 runs
each, 0 faults (`variants.json`):

| Form | Lanes whose source lane i - k is in the same segment | Lanes whose source is outside the segment |
| --- | --- | --- |
| fmadd16, 4-lane segments, k = 2, 3 | read lane i - k (exact) | **0**, deterministic |
| fmadd32, 4-lane segments, k = 1, 2, 3 | read lane i - k (exact) | **undefined**: garbage that changes between runs |
| fmadd32, 2-lane segments, k = 1 | read lane i - 1 (exact) | **undefined** |

So every k works inside a segment; for **fmadd32 in the segment modes the boundary lanes' results must be discarded or
masked** (as a segmented scan does with its select), while fmadd16 gives 0 there. The simulator can model the
in-segment lanes for all k and the fp16 zeros; the fp32 boundary lanes stay unmodelled (undefined).

## Cost (`run_bench.py`, cycles; `bench.json`)

| Op | Dependent latency | Issue per SIMD group (8 chains) | GPU-wide lanes / cycle / core |
| --- | --- | --- | --- |
| `fmadd32` | 2.0 | 2.0 | 44.0 |
| `simd_shuffle_up r, r, 1` | 4.84 | 1.99 | 64.3 |
| **`fmadd32_lane` k = 1** | **3.91** | **2.48** | **30.9** |
| `fmadd32_lane` k = 15 | 3.90 | 2.48 | 30.9 |
| `fmadd16_lane` k = 1 | 3.91 | 2.24 | 39.3 |

Against `shuffle up` + `fma` (6.84 cycles dependent, ~4.0 issue cycles, 26.1 lanes / cycle / core for the pair), the
lane form is **1.75x faster in latency, 1.6x in issue and 1.18x in throughput**, independent of k. Use it wherever a
scan or stencil step is a shifted fma.

`bench_ops.py` gained `simd_shuffle_up1`, `fmadd32_lane1`, `fmadd32_lane15`, `fmadd16_lane1`; the lane forms need
the Rust assembler, so run the bench with `coverage.install()` first:
`python3 -c "import sys; sys.argv=['run_bench.py','--ops','fmadd32_lane1']; import coverage; coverage.install(); import run_bench; run_bench.main()"`.
