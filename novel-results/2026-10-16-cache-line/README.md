# The cache line is 64 bytes at every level (L1, L2, SLC / DRAM fill)

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, GPU clock held at
its top state (`scripts/clock_keeper.py`). Simulator task safe-03 step 1.

## Claim and scope

**Test ("is the neighbour free?"):**
- Elements 1 KiB apart are visited in a random single cycle. Each hop makes two dependent loads: the word at the
  element start, then the word at offset d, which holds the next element's index.
- When d is inside the line the first load fetched, the second load hits that level; otherwise it misses it.
- 3 element counts × 14 offsets, 200,000 hops per dispatch, 4 repeats, with the long-command clock keeper (v2).
  Every kernel and table first passed the simulator's `agx_run` oracle, and every readback was exact.

| elements (where the line lives) | d = 4-60 B | d = 64-192 B | step |
|---|---|---|---|
| 64 (both lines stay in L1) | 110.6 | 110.9-111.0 | none: both hit L1 |
| 1,024 (L2-resident: second load misses L1) | 170.4-171.6 | 232.4-232.8 | **+62 ns at 64 B** |
| 65,536 (64 MiB span: second load misses L2) | 447-449 | 672-788 | **+224 ns at 64 B** |

- **L1 lines and L2 lines are both 64 bytes:** 60 B is free and 64 B is not.
- There is **no second step at 128 B**, so there is no 128-byte line with 64-byte sectors.
- A +5 ns rise at 512 B (1,024 elements) is unexplained.

This contradicts the published "global cache line 128 B" (philipturner/metal-benchmarks, Apple 7 / 8, through
Metal). See `docs/external-knowledge.md`.

**Correction:** the first run of this test used the first clock keeper, which evicts L2 at every one of its command
boundaries (`2026-10-16-l2-command-boundary`). It showed the same 64 B step, but with inflated L2-level costs. It is
kept as `neighbour-old-keeper.json.gz`.

## A failed first approach

A *sequential* pointer chase (element i → i + 1 at stride s) gave confusing numbers:
- one pass per dispatch cost SLC latency even for a 64 KiB table;
- 8 passes per dispatch did not warm it;
- repeats jumped between ~174 and ~300 ns.
It is kept as `sequential-chase-*.json.gz`, but it is unexplained and not used for any claim
(`notes/failed-approaches.md`).

## Reproducer and evidence

- `make cache-line`: GPU, with the clock keeper.
- `make verify-cache-line`: offline, 11 checks.
- Runner: `scripts/run_drm_neighbour.py`.
- [Evidence](../../results/2026-10-16-cache-line/), with harness snapshots.

## Implications

- **Coalescing / cost model:** a 32-lane access to 32 consecutive 4-byte words touches 2 lines, not 1. Strided
  patterns cost one line per 64 bytes.
- The simulator's cost model should use 64-byte segments. The `coalesce` probe's "stride 16 = 5.96x" (safe-02 §2)
  should be re-fitted with 64-byte lines.
- **CUDA:** 128-byte-aligned "fully coalesced" accesses on NVIDIA map to two 64-byte lines here. No change in
  correctness; only cost.
