# TLB reach 256-384 MiB; L1 8 KiB, L2 spills by 1 MiB; SLC vs DRAM barely separable by latency

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, GPU clock held by the
long-command `clock_keeper.py`. Simulator task safe-03 steps 2-3.

## Claim and scope

All runs are random single-cycle pointer chases by one SIMD group (`scripts/run_drm_compute.py --kind chase`). Every
kernel and table passed the simulator's `agx_run` oracle first (`scripts/sim_gate.py`), and every readback was exact.

**TLB (one element per 16 KiB page, against the same number of 64 B lines packed together):**

| elements | packed lines (ns/hop) | one per page | difference |
|---|---|---|---|
| 16-128 | 40.3-40.8 | 40.4-40.8 | 0 |
| 256-4,096 | 93-123 | 93-119 | 0 |
| 8,192 | 151-157 | 152-158 | ≤ 2 |
| 9,216-16,384 | 157-371 | 161-362 | ± 20 (L2-spill noise) |
| **24,576 (384 MiB)** | 356 | **477** | **+121** |
| **32,768 (512 MiB)** | 368 | **534** | **+165** |

**The GPU TLB covers between 256 and 384 MiB of 16 KiB pages** (≥ 16,384 entries, or larger mappings or a
page-walk cache). Beyond that, a miss adds 120-165 ns. The 2026-10-10 study bounded the cost at 16,384 pages to
≤ 32 ns, which agrees.

**Cache levels (packed lines):**
- L1: ~40 ns up to 8 KiB.
- L2: 93-123 ns from 16 to 256 KiB, spilling gradually (151 ns at 512 KiB, 284-371 ns at 1 MiB, 368 ns at 2 MiB).
  This matches the published ~1 MB L2 for M2 Max.
- The line size is 64 B at every level (`2026-10-16-cache-line`).

**SLC capacity:**
- Full-coverage chases (twice the elements per dispatch) at 16-96 MiB rise only gradually: 416, 423, 448, 448, 459,
  462, 461, 466, 466 ns.
- There is no sharp edge near the published 48 MB SLC, because SLC hits and DRAM differ by only ~10-15% in latency
  from the GPU.
- **The SLC capacity cannot be read from latency.** A bandwidth probe is needed (open). The CPU-sharing variant of
  the SLC test was not run.

## Reproducer and evidence

- `make verify-memory-parameters`: offline, 10 checks.
- [Evidence](../../results/2026-10-16-memory-parameters/): the TLB and SLC records with harness snapshots.
  `tlb-pages` / `tlb-lines` were taken under the first, L2-evicting keeper and are kept for reference only.

## Implications

- Address spaces beyond ~256 MiB of randomly touched 16 KiB pages pay TLB misses of 120-165 ns. Large CUDA
  allocations with random access, such as hash tables or graphs, should prefer locality.
- L2 is ~1 MiB for the whole GPU, so cross-core sharing patterns hit the SLC early.
- The simulator's L1 / L2 / SLC parameters (`rust/src/cost.rs`, `make verify-memory-model`) should be checked against
  these curves: 64 B segments, ~1 MiB L2.
