# B15: `simd_matrix_fmadd32` / `simd_matrix_fmadd16` on G14C: operand layout, exact arithmetic, cost (2026-10-21)

Blocker B15 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM, battery power (timings in
cycles against an in-dispatch reference). Mesa 25.3.6 exposes no cooperative-matrix extension, so applegpu's encoding
(0x6f with bit 27, 8 bytes) was run through `probe_variants.py`: the surrogate `fmadd32 r30, r30, r31, r29` (8 bytes)
makes the whole program run in agx_run first; only the instruction differs. One SIMD group per dispatch. 0 faults;
hang budget unchanged.

## Layout (`b15_map.py 32|16`, `map32.json`, `map16.json`)

Each lane holds two elements of each 8x8 matrix: for fp32 the register pair (`r8_r9`: slot 0, slot 1), for fp16 the
two halves of one register (`r8l_r8h`). With element index q = 2 lane + slot:

    row(q) = ((q >> 2) & 3) + 4 (q >> 5)        col(q) = (q & 3) + 4 ((q >> 4) & 1)
    i.e. lane t, slot s:  row = 4 (t / 16) + (t / 2) % 4,   col = 4 ((t / 8) % 2) + 2 (t % 2) + s

**The same layout for A, B, C and D, and for both widths.** It is exactly the fixed layout the `agx.mma` op already
assumes. 64 one-hot-A experiments (A[r][k] = 1, B[j] = j + 1) per width put row k of B into row r of D, and C goes to
D unchanged: **D = A B + C** (no transposes).

## Arithmetic (`b15_arith.py`, `b15_arith16.py`; 120 random A, B, C sets each = 7,680 elements)

| Model | fp32 | fp16 |
| --- | --- | --- |
| **acc = C; acc = fma(A[r][k], B[k][c], acc) for k = 0, 1, ..., 7, rounded every step** (in the operand type) | **7,680 / 7,680** | **7,680 / 7,680** |
| the same chain for k = 7 .. 0 | 3,498 | - |
| one rounding of the exact sum | 4,426 | 4,368 |
| pairwise tree | 3,832 | - |
| products rounded, then summed | 5,310 | - |
| fp16: chain kept in fp32, rounded to fp16 at the end | - | 4,368 |

So each element is an **in-order chain of 8 fused multiply-adds** (fp32: round to nearest even with the unit's usual
flush of denormals; fp16: denormals kept, overflow to inf). This is what PTX `mma.sync` with `.f32` accumulation does
not promise either way, so ZLUDA can use it for f32 / f16 `mma` and the backend for `agx.mma`; the simulator can model
it exactly.

## Cost (`run_bench.py`, `bench.json`; cycles)

| Op | Dependent latency | Issue per SIMD group | GPU lanes / cycle / core |
| --- | --- | --- | --- |
| `fmadd32` | 2.0 | 2.0 | 43.1 |
| **`simd_matrix_fmadd32`** | **16.2** | **15.5** | 8.4 (one 512-FMA instruction per 3.8 cycles per core = **~134 FMA / cycle / core**) |
| **`simd_matrix_fmadd16`** | **16.3** | **15.4** | 8.3 |

Against scalar `fmadd32` (43 FMA / cycle / core) the native form gives about 3x the FMA throughput, and against the
current emulation (24 shuffles + 16 FMAs per 8x8 tile, ~80 issue cycles) about 5x per tile, without the gathered-row
register pressure. `bench_ops.py` gained both forms (run with `coverage.install()` first, as for B18).

## An unexplained intermittent

In one ~10-minute window, about 1 % of dispatches (13 of ~1,500) read D back as the readback buffer's initial zeros;
D initialised to a sentinel was never left unwritten, and inserting 1-8 instructions before the stores made no
difference (`hazard.jsonl`). Afterwards **0 of 2,700** runs failed, with the readback buffer pre-filled with a second
sentinel and the surrogate interleaved as a control. It looks like stores of a whole dispatch going missing rather than
the instruction, but it is not explained; the recorded experiments that hit it (2 of 130) were re-run and match the
layout exactly.
