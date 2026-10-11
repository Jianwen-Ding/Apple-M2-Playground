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
Reproduce: `make grid-cap`.

## Follow-up: shapes, Z, and grids up to 2^30

`shapes.json` (control main, `AGX_LOCAL_X/Y`, `AGX_GLOBAL_Y/Z`; grid cap raised to 2^30 threads):

- Z behaves like Y: 2^16 / 2^20 / 2^24 threads as 32×1×N take 10.5 / 97 / 1491 µs, same as Y.
- **Time follows the workgroup count.** 2^24 threads, fixed 32-lane output: 32-thread groups
  1489 µs, 64 → 691, 256 → 182, 1024 → 133 µs. That is ≈2.7 ns per workgroup (whole GPU)
  for groups of 32–256 threads, falling to ≈8 ps/thread at 1024-thread groups.
  2^20 threads with distinct stores: local X 32 → 109 µs, 64 → 59, 256 → 37, 1024 → 20 µs.
- 2^24 distinct stores (64 MiB) with 1024-thread groups: 185 µs ≈ 360 GB/s of writes.
- Long dispatches run faster from the 2nd–4th submit on (the same 2^27 launch went
  1.02 → 0.47 ms), so per-thread rates above 2^25 vary with the GPU clock ramp. Take the minimum.

`coverage.json` (`scripts/run_drm_grid_coverage.py`, `make grid-coverage`): global 32 × 2^k/32,
local 32×32. Rows with `y % 2^s == 0` store `y` to `out[8 + (y >> s)*32 + x]`
(index bounds-checked against `count`). s = 0 up to 2^20 (every row) and s = k − 20 above
(2^15 rows sampled evenly over the whole Y range). **Every checked word matched at
2^16, 2^18, 2^20, 2^22, 2^24, 2^26, 2^27, 2^28, 2^29 and 2^30 threads**: the hardware runs the whole
grid with correct `thread_position_in_grid.y` to 2^30 threads (2^25 rows). Time is linear
once the clock has ramped: 2^28 / 2^29 / 2^30 → 1.16 / 2.32 / 4.61 ms ≈ 4.3 ps/thread.

Not tested: grids above 2^30 threads, or global sizes whose X·Y·Z product reaches 2^32.
