# Occupancy evidence — 2026-10-11

`scripts/run_drm_occupancy.py`, 2^20 lanes, 8,000-step dependent iadd chain between a per-core
atomic increment (returned) and decrement. Each point records the peak lanes in flight on any
core, peak SIMD groups (/32), whether every counter returned to 0, and firmware time.

| File | Workgroup | Register counts |
| --- | --- | --- |
| `lx128-sweep.json.gz` | 128 lanes | 16–248 step 8, two repeats |
| `lx32-low.json.gz` | 32 lanes | 16–64 |
| `lx64-points.json.gz`, `lx256-points.json.gz` | 64 / 256 lanes | 16, 48, 96, 160 |
| `loop-timing-summary.txt` | 32 lanes | timing sweep: pass, halves, ok, min/median/max firmware ns (`run_drm_compute.py --kind loop --steps 16 --lengths 64`) |

Offline: `scripts/verify_occupancy.py` (`make verify-occupancy`).
