# In-shader clock runs — 2026-10-11

`scripts/run_drm_cpu_clock.py` with `tests/drm_compute.c` `AGX_CPU_CLOCK=0`. 32 lanes;
results are from the last of the submissions per configuration. Checked by
`scripts/verify_in_shader_clock.py` (12 checks).

| File | Contents |
| --- | --- |
| `same-line-stale.json` | First run: two reads of the same line, normal/coherent × flush on/off × 0–100,000 trips. Always identical values, which come from a live CPU write. |
| `barrier-variants.json` | 10,000 trips: second-line read, and same-line reads after each Mesa barrier, normal and coherent load |
| `linearity.json` | Coherent + `device_barrier_1` / `unknown_barrier_1`, and second-line reads, at 0–100,000 trips with flush on/off, against firmware time |
