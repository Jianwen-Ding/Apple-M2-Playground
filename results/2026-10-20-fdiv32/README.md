# div.f32 evidence (2026-10-20)

`exact.json.gz`: hardware (`hw-<op>-<data>[-mode]`) and simulator (`sim-...`) outputs of `run_drm_fdiv32.py` for the edge
(22,912 lanes) and in-domain fast (131,072 lanes) datasets. `cost.json.gz`: `cost/` (clock not held) and `cost-keeper/`
(clock held) chains `<op>-<data>-k<K>`; output arrays dropped. Check: `make verify-fdiv32`. Limits: one device, AC power.
