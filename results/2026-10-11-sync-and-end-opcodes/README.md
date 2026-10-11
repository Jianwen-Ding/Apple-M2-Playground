# Sync and ending-opcode runs — 2026-10-11

`scripts/run_drm_sync_probe.py`, direct DRM, `CONFIRM_GPU_FAULTS=1`. Checked by
`scripts/verify_sync_and_end.py` (34 checks). Timing records drop the per-lane
table and keep only `sr20_distinct` (the number of cores that ran the dispatch).

| File | Suite | Contents |
| --- | --- | --- |
| `barrier-device.json` | barrier | 2/4-group delayed-flag test through device memory: references, 0x18, 0x78, zero forms, `memory_barrier` + candidate |
| `barrier-tgmem.json` | barrier | Same with the flag in threadgroup memory |
| `tgcheck.json` | tgcheck | Threadgroup-memory exchange (lane i reads lane n-1-i), 1/2/4 groups |
| `memwait-floor.json` | memwait | 50,000-trip loops: none/device load/device store × candidates |
| `tgwait-floor.json`, `atomic-floor.json` | tgwait | Threadgroup load/store and device atomic × candidates |
| `scope-floor.json`, `scope-workgroups-floor.json` | scope | 1–8 SIMD groups in one workgroup; 8/64/256 one-group workgroups |
| `endpend.json`, `endfollow.json`, `endcost.json` | end* | Pending stores, self-ending vs skip, cost of ending 2,048 groups |
| `clock-flip.json` | memwait | Short dispatches: the same loop at 831 µs, then at 382 µs, on the same core |
| `floor-stability.json` | scope | 50 long dispatches: floor 6,548–6,584 µs |

Discarded analyses: per-iteration costs from short dispatches (state flips) and
bracketed short-dispatch pairs (too few stable pairs). Both are superseded by the
50,000-trip floor method.
