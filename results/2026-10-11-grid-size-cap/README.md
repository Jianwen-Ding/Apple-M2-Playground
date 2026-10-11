# Grid-size cap runs — 2026-10-11

`scripts/run_drm_compute.py --kind control` with `tests/drm_compute.c`, caps raised from 65536
to 2^24 threads. The control main stores `0x12345678` to `out[8 + x]` for `x < count`.
Local size 32×1×1, 2 submits per size, one process per size, sizes stepped one power of
two at a time. Every run's whole output buffer (guards and tail included) matched the oracle.

| Form | Launch | Output |
| --- | --- | --- |
| `x` | global X = count = 2^16..2^24 | grows with the grid (up to 64 MiB) |
| `y` | count = global X = 32, `AGX_GLOBAL_Y` = 2^11..2^19 | fixed at 32 lanes, every Y row stores to the same words |

`runs.json`: per-run thread count, CDM stream bytes, firmware start→end ns for both submits.

Firmware time (min of 2) — fixed overhead dominates below 2^19, then about 89 ps/thread
(Y) and 92 ps/thread (X, distinct stores), i.e. ~11 G trivial threads/s on the 38-core M2 Max:

| threads | X µs | Y µs |
| --- | --- | --- |
| 2^16 | 11.3 | 10.5 |
| 2^18 | 36.6 | 28.0 |
| 2^20 | 109.2 | 98.2 |
| 2^22 | 406.6 | 377.7 |
| 2^24 | 1548.8 | 1489.2 |

No kernel GPU fault/timeout messages. The earlier host crash at 2^20 (see
`notes/failed-approaches.md`) did not reproduce, so a 2^20 grid alone did not cause it.
Not tested: grids above 2^24, local sizes other than 32, very large Z.
Reproduce: `make grid-cap`.
