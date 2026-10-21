# B18: the lane-offset fmadd forms the compiler emits, recorded and timed (2026-10-21)

Blocker B18 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM, battery power (timings are
in cycles from an in-dispatch reference, so the clock state cancels). 0 faults; hang budget unchanged.

## Recorded

`coverage.py record --area fmadd_lane_b18,fmadd_lane_b18_masked`: all 34 catalog forms (k = 1..15 for fmadd32 and
fmadd16, segments of 4 and 2 lanes for both widths, partial masks) recorded deterministic on the first run. 28 new
files (6 names coincide with the earlier `fmadd_lane` area). **`suite_check`: fmadd_lane_b18 20 / 20, fmadd_lane_b18_masked
8 / 8 exact** (plus the earlier fmadd_lane 16 / 16 and fmadd_lane_masked 8 / 8). The simulator's model of the form is
confirmed for everything `agx.fma_lane_shift` emits, so the native G14 lowering can be enabled.

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
