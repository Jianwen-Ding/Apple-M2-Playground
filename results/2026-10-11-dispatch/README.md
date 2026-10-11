# Whole-dispatch evidence (2026-10-11)

* `dispatch.json`: 29 dispatches (25 + 4 divergent `diverge<k>`) (`scripts/dispatch_probes.py`): case, grid, workgroup, register halves, table words,
  firmware durations `fw_ns` (8 back-to-back after a warm-up dispatch), `min_us`, and the submitted main shader in
  `cases/` (harness uniforms u4 = 0, u5 = grid).
* `placement.json`: per-core workgroup counts for 38–608 workgroups of 256 and 64 lanes (`scripts/wg_placement.py`,
  200 trips); `placement-long.json`: 38 and 152 workgroups with 3,000–6,000 trips.
`make verify-dispatch`.
