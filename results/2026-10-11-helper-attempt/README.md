# Custom helper program attempts — 2026-10-11 (both: probable GPU hang/recovery; helper probing dropped)

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

## Second attempt: Mesa-shaped (`helper-mesa-shaped.json`)

The owner approved one retry shaped like Mesa's helper: only argument and core
reads before the first `doorbell 32`, registers r0–r6, the request log between
doorbells, and a 16-selector scan only after END. Result: **the same signature**.
502.7 ms, no firmware timestamps, main oracle correct, and this time **no helper
output at all**, not even the first log entry written right after the first
doorbell. A control dispatch afterwards passed.

So the helper is launched on the cores with work (attempt 1 wrote from cores 0
and 1), but its first doorbell never returns: no request, not even END, reaches
it, and the firmware ends the command after ~0.5 s. With Mesa's real helper,
requests and END evidently do arrive. The missing condition is not identified.
Candidates: a `cfg` value or helper-binary tag bits beyond bit 0, a main shader
that declares stack use (Registers spill size), or setup the firmware performs
only for Mesa-shaped scratch headers at `helper.data`.

Per the agreed rule (another hang ends helper probing), no further helper runs
were made. Both runs are owner-approved probes that each caused one ~0.5 s
stall; neither left the GPU unusable.
