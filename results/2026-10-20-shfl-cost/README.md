# shfl cost and register-amount evidence (2026-10-20)

`chain.json.gz`: `run_drm_shfl_cost.py hardware` (7 kinds, K 1/64/128, 5 repeats). `chain-native.json.gz`: the native kinds at K
64/1024/2048, 7 repeats. `chain-sim.json.gz`: simulator outputs for the K=64 exactness check. `regamt-{hw,sim}.json.gz`:
`run_drm_shfl_regamt.py` outputs (240 groups, 8 programs). Check: `make verify-shfl-cost`. Limits: one device, AC power, firmware time.
