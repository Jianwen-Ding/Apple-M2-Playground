# Atomics evidence — 2026-10-11

Direct DRM, `tests/drm_compute.c`, one repeat per dispatch, GPU control dispatch passed before
the run. Offline check: `scripts/verify_atomics.py` (`make verify-atomics`).

| File | Runner / mode | Content |
| --- | --- | --- |
| `device-all.json.gz` | `run_drm_atomic.py` noret, lane, shared × 11 ops | 33 dispatches, 64 lanes; operands T, X, Y stored |
| `device-casrace.json.gz` | `--ops cmpxchg --modes casrace` | all compares = init; one winner |
| `device-count4096.json.gz`, `device-count65536.json.gz` | `--ops add --modes count` | returns are a permutation; final = init + n |
| `tg-all.json.gz` | `run_drm_tg_atomic.py` noret, lane, shared × 11 ops + casrace | 34 dispatches, one 32-lane workgroup, 2 KiB declared |

Table layout (u8_u9 words): T at 0, X at 64, Y at 128, contended device word at 256,
threadgroup read-back at 192. Initial contended value 0x40000000.
