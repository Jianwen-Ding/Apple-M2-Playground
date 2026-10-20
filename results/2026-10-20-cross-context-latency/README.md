# Cross-context latency evidence (2026-10-20)

`record.json.gz`: `run_drm_neighbour.py` records. `on1/off1/on2/off2` interleaved keeper A/B; `longkeeper2` one long-lived
keeper process; `neigh-k-long` / `neigh-k-short` keeper kernels with 63 ms / 0.64 ms commands; `ctx-*` same-context second
workgroups (`--lanes 64 [--busy]`); `rerun-all-offsets-nokeeper` the cache-line offsets without the keeper. Check:
`make verify-cross-context`.
