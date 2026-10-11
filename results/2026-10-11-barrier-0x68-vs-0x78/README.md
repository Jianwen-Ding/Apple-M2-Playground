# Barrier stress runs (0x68 vs 0x78) — 2026-10-11

`scripts/run_drm_barrier_stress.py`: 16,384 threads, 2,000 iterations, 3 submissions per job.
Counts are from the last submission. `scripts/verify_barrier_stress.py` runs 14 checks.

| File | Contents |
| --- | --- |
| `matrix-shared8k.json` | Full matrix (tg/dev × 64/128/256 lanes × barrier × pre-sequence), 8 KiB declared. The tg rows at 128/256 lanes are a capacity artifact; the dev rows are valid. |
| `tg-matrix-shared32k.json` | Threadgroup-memory rows rerun with 32 KiB declared |
| `n256-by-group.json` | 256-lane rows with errors broken down per reading SIMD group |
| `dist2-sizes256.json`, `dist4-sizes256.json` | Partner 2 and 4 SIMD groups away |
| `dist1-sizes512-1024.json` | 512 and 1,024-lane workgroups |
| `tg-capacity.json` | `run_drm_tg_capacity.py`: exchange exactness against declared size and offset |

The 64-lane `wait` control with 32 KiB declared showed 0 mismatches: with one workgroup per
core, its 2 groups ran in lockstep. Controls with 4 or more SIMD groups always showed stale reads.
