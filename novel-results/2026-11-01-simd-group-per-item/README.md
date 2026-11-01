# A serial loop per thread loses 3-15x to the same loop per SIMD-group (lanes over the elements, shuffles to combine)

Status: confirmed on one device (M2 Max G14C), five of our own library kernels (ZLUDA's replacement cuSOLVER and
cuBLAS), timed end to end through the CUDA driver API on a warm GPU clock and checked against CPU references.

## Claim

Kernels that gave one thread a whole vector to walk (a column of a matrix, a column pair, a right-hand side) ran
3-15x slower than the same arithmetic with a SIMD-group per vector, its 32 lanes taking every 32nd element
(neighbouring lanes, neighbouring addresses) and combining by `subgroup_reduce` or broadcasting by `shuffle idx`.
Nothing else changed: the formulas, the number of launches and the bytes touched are the same.

| Kernel (f32) | Thread per item | SIMD-group per item |
|---|---|---|
| Householder reflector of a 32-column QR panel, 4096 x 256 geqrf | 374 ms | 24.6 ms (one workgroup per panel) |
| One-sided Jacobi round, gesvd n 512 | 1287 ms | 207 ms |
| One-sided Jacobi round, syevd n 512 | 1117 ms | 240 ms |
| Triangular solve of <= 64 blocks, trsm 4096 x 64 | 30.0 ms | 6.3 ms (vector in registers) |
| gemv without transposition, 1024 x 16384 | 2046 us (33 GB/s) | 217 us (309 GB/s, columns split into chunks) |

## Explanation (from the measurements, not from documentation)

- With a thread per item, the 32 lanes of a SIMD-group read 32 different columns at once, 32 different cache lines
  per load instruction; with lanes over one column a load instruction covers one or two lines. The read-bandwidth
  limit ([read bandwidth](../2026-11-01-read-bandwidth/README.md), ~350 GB/s) is reached only in the second form:
  gemv went from 33 to 309 GB/s.
- Thread per item also leaves the GPU nearly empty when the items are few: 64 right-hand sides or n/2 column pairs
  are 64-256 threads for a 38-core GPU. Per-item SIMD-groups give 32x the threads for the same work.
- For gemv the fix is the same with a different split: rows were few (1024 threads), so the columns were cut into
  chunks to reach ~64K threads; with 8192+ rows a thread per row already reaches bandwidth (16384 x 1024: 192 us
  either way).

## Implications

- For library kernels, "one thread does a dot product / substitution over n elements" is a red flag on AGX unless
  there are tens of thousands of items and the threads read neighbouring addresses.
- A serial dependency along the vector (substitution) still parallelizes across lanes when each lane keeps its
  elements in registers and the solved value is broadcast by a shuffle: 64 steps, no memory traffic inside the loop.

## Reproducer and evidence

ZLUDA (branch claude/perf-air-agx): `zluda_solver_agx/tools/qrbench.c`, `eigbench.c`, `zluda_blas_agx/tools/l2bench.c`,
`trsmcheck.c`; the old paths stay behind `ZLUDA_AGX_QR_PANEL=0`, `ZLUDA_AGX_JACOBI_SG=0`, `ZLUDA_AGX_TRSM_SG=0`,
`ZLUDA_AGX_GEMV_SPLIT=0` for A/B runs. Commits c3425c9, 86f229b, 6204102, 715dc59; numbers and checks in their
messages and in ZLUDA docs/src/agx.md.

Uncertainty: wall-clock per library call (launch cost ~2-5 us included); one device; the split between the
coalescing effect and the occupancy effect was not separated by a dedicated probe.
