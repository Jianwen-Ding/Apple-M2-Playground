# Custom helper program attempt — 2026-10-11 (stopped: probable GPU hang/recovery)

`helper-first.json` is the full record of one `scripts/run_drm_helper.py`
submission (owner-approved as a risky, unemulatable probe). It holds the helper
bytes, a complete disassembly, the drm_compute event log and the per-core table
regions.

Observed:
* The submit and syncobj wait returned success, and the main control shader's
  whole-buffer oracle passed.
* Host submit-to-signal took **502.9 ms** (normal: 0.1–0.6 ms). The firmware
  start/end timestamps were **not written** (both 0).
* The helper ran on cores 0 and 1 (the two cores with work). Each wrote only
  selectors 0–6 (all 0) of its 256-entry scan, then nothing; the request log is empty.
* A control dispatch immediately afterwards passed; the GPU stayed usable.

Interpretation (not confirmed: dmesg needs root): the helper was stopped after
about 7 store + `wait 0` iterations, and the command finished through a firmware
timeout/recovery path. The data do not distinguish among candidate causes: a time
or instruction budget for helper code before its first doorbell, a register
allocation smaller than the r0–r12 used, or `wait` behaving differently in helper
context. Mesa's helper rings its first doorbell almost immediately and never
waits on memory before it.

No further helper runs were made pending owner review.
