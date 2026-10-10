# AGX loop timing evidence — 2026-10-10

Run records from `scripts/run_drm_compute.py --kind loop` (direct DRM, no Mesa),
copied unchanged from `/scratch/apple-m2-playground/drm-compute/runs/`. Each
record holds the hand-built USC/CDM words, the emulator-gate entry per variant,
the whole-buffer oracle result, and per-submit firmware start/end timestamps.

| Files | Contents |
| --- | --- |
| `first-loop.json` | First hardware loops: K = 1, 3; 2 iadd steps; 33 lanes |
| `trip-scale.json` | K = 10..100000, 1 iadd step, 3 submits each |
| `steps-m<M>-<i>.json` | iadd dependent, K = 2000, M = 0/8/16/32/64 (m0 twice: drift check) |
| `<kind>-c<chains>-m<M>.json` | K = 2000, 6 submits: lowest-state latency/issue matrix |
| `fadd4-c<chains>-m<256,512>-k500.json` | Large-body runs exposing the short-body 4-chain artefact |
| `warm-*.json` | 40 submits each: clock ladder and top-state plateau |
| `groups-<lanes>.json` | 32..38912 lanes, 30 submits: SIMD groups per core at top state |
| `verification.json` | Output of `make verify-loops` |

Report: [loops and ALU timing](../../experiments/control-flow/loops-and-alu-timing.md).
