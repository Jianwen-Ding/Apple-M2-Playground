# A kernel running in another GPU context adds ~190 ns to far-memory loads; the clock keeper inflated earlier latencies

Status: one device (driver-reported M2 Max G14C B1), direct DRM, the cache-line "neighbour" pointer chase
(`scripts/run_drm_neighbour.py`, simulator-gated, oracle-exact). 0 faults.

## Results (ns per hop, one SIMD group, minimum of 8 repeats)

| Condition | 64 MiB span, d = 4 / 64 | L2-resident (1,024 elements), d = 4 / 64 |
|---|---|---|
| nothing else on the GPU | **256 / 407** | 164 / 217 |
| clock keeper running (another process: 64-lane ALU-only kernel on ≤ 2 cores), interleaved A/B, 2 rounds | **448 / 640-654** | 170 / 230-233 |
| keeper as one long-lived process (64 × 64 commands, no process churn) | 448 / 672 | 170 / 232 |
| keeper commands 63 ms long | 449 / 650 | 170 / 232 |
| keeper commands 0.64 ms long | 445 / 658 | **238 / 437** |
| same context: a second workgroup also chasing | 290 / 447 | 164 / 217 |
| same context: a second workgroup ALU-busy (~87% overlap at d = 4) | 256 / ≥ 407 (noisy) | — |

- **Another context executing concurrently costs ~190 ns per far-memory load, even when its kernel is ALU-only and on other
  cores.** Neither process churn nor command boundaries explain it (long-lived process, 63 ms commands). Concurrency within
  one context does not reproduce it. A translation/MMU effect across address spaces is plausible but not established.
- **The L2-level penalty is a separate effect.** It scales with the other context's command rate, consistent with the known
  [L2 eviction at command boundaries](../2026-10-16-l2-command-boundary/README.md).

## Corrections to earlier findings

- [Cache line](../2026-10-16-cache-line/README.md): the 64-byte step is confirmed without the keeper. Its absolute L2 and
  64 MiB latencies (170 / 232 and 448 / 670 ns) include the keeper penalty; the values without it are 164 / 217 and
  256 / 407 ns.
- [Memory parameters](../2026-10-16-memory-parameters/README.md) (TLB reach and miss cost, L2 / SLC latency curve) was
  measured with the keeper. **Its far-memory latencies and possibly its TLB conclusion need re-measurement without it.**
  That was not done in this session.
- Any latency measured with `clock_keeper.py` running should be treated as an upper bound. See
  [failed approaches](../../notes/failed-approaches.md).

## CUDA relevance

Concurrent GPU work from another process (another CUDA process, and possibly the compositor) can inflate a kernel's
DRAM/SLC-level latency by ~75%. Latency-bound kernels should be benchmarked with the GPU otherwise idle.

## Reproduce

`python3 -B scripts/run_drm_neighbour.py --elements 65536,1024 --offsets 4,64 --repeats 8 [--lanes 64 [--busy]]`, with and
without `scripts/clock_keeper.py`. Offline: `make verify-cross-context` (7 checks against
[results/2026-10-20-cross-context-latency](../../results/2026-10-20-cross-context-latency)).
