# Direct DRM compute evidence — 2026-10-10

Run records from `scripts/run_drm_compute.py` (harness `tests/drm_compute.c`, no
Mesa/Vulkan). Each variant stores the hand-built USC words and CDM stream as hex,
GET_PARAMS identity, whole-buffer oracle result, and per-submit samples:
`fw_ts` (firmware start/end of the compute command), `drm_time` (GET_TIME
before submit / after wait) and `host_ns`.

| File | Contents |
| --- | --- |
| `control.json` | Unchanged control main, 257 lanes, 4 submits |
| `fadd4.json` | fadd32 chain 0/4096/16384/65536, 32 lanes, 8 submits each |
| `iadd8.json` | iadd chain 0/16384/32768, 32 lanes, 6 submits each |

Checked by `make verify-timestamps` (checks `drm-*`).
Report: [direct DRM compute](../../experiments/baseline/direct-drm-compute.md).
