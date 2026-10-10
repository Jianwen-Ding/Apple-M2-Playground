# Pointer-chase load-latency evidence — 2026-10-10

Run records from `scripts/run_drm_compute.py --kind chase` (direct DRM), copied
unchanged from `/scratch/apple-m2-playground/drm-compute/runs/`. Each variant
records footprint, stride, hops, seed, the emulator gate, the exact final-index
oracle, and per-submit firmware timestamps. Tables are regenerated from
(footprint, stride, seed) by `agx_loop.chase_table` and are not stored.

| File | Contents |
| --- | --- |
| `first-chase.json` | First hardware chase: 4 KiB, 6 hops |
| `curve-coarse.json` | 4 KiB..256 MiB, 9 sizes, 8 submits |
| `curve-fine.json` | 2 KiB..256 MiB, 21 sizes, 30 submits (main curve) |
| `l2-clock-fresh.json` | 32 KiB in a fresh process: second-level latency across the clock ladder |
| `page-stride.json` | One line per 16 KiB page, 16..16384 pages |
| `verification.json` | Output of `make verify-memory` |

Report: [load latency](../../experiments/memory/load-latency.md).
