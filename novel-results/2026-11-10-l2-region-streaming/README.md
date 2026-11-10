# Sequential re-reads of a per-core region cost almost the same at 16 KB and 2 MB, and do not slow down as cores are added

Status: confirmed on one device (M2 Max G14C), 2026-11-10, own probe kernel (AGX-Performance-Simulator
`scripts/probe_l2_share.py`), agx_run_hw `--back-to-back 500`.

## Result

N workgroups of 256 threads (one per core), each looping 2000 trips over its own REGKB region: per trip 4 coalesced
loads (consecutive words per lane, the loads 1 KB apart), `wait`, 4 fadds; the next trip starts 4 KB on, wrapping.
Disjoint regions.

| REGKB | N = 1 | 4 | 8 | 16 | 32 |
|---|---|---|---|---|---|
| 16 | 314 | 326 | 335 | 336 | 337 |
| 256 | 328 | 340 | 348 | 349 | 349 |
| 512 | 341 | 352 | 360 | 361 | 361 |
| 2048 | 418 | 426 | 432 | 432 | 432 |

- ~+7% from 1 to 8 cores (one cluster), then flat to 32 cores (all clusters), at every region size: no shared-cache
  capacity or bandwidth cliff even with 32 x 2 MB = 64 MB streamed (beyond the system-level cache).
- 512 KB per core costs only 8% more than 16 KB, 2 MB 33% more: sequential re-reads are prefetched or the level
  below L1 is much larger than 256 KB per core.

## Implications

- Not the cause of the MMQ full-grid undershoot (no multi-core interference).
- AGX Performance Simulator: up to 256 KB it matches (322-335 us); beyond its 256 KB per-core L2 it charges SLC /
  DRAM latency per wait: 813 us at 512 KB (hw 341), 794-897 at 2 MB (hw 418-432). A stream prefetcher (or a larger L2
  for sequential lines) is missing. Not changed yet.

## Reproducer and evidence

`T=2000 N="1 4 8 16 32" REGKB="16 64 256 512 2048" python3 scripts/probe_l2_share.py both`.
[Evidence](../../results/2026-11-10-l2-region-streaming/).
