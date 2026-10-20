# fp64 directed rounding evidence (2026-10-20)

`record.json.gz`: `run_drm_softfp64.py hardware --op add|mul|fma --round rz|rm|rp` records (lanes, instructions,
per-run mismatch counts against the exact rational reference). Check: `make verify-fp64-modes`.
