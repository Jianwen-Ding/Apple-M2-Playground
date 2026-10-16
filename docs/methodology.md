# Probe method and evidence

## A single experiment

Record a question and hypothesis before running. Identify the device, driver,
kernel, header hashes, compiler, input bytes, expected result, and command.
Begin with a known-good control; vary one instruction field, operand, or input
at a time. Preserve the output and compare with an independent host result.

Offline assembler/emulator checks validate the toolchain or model. Hardware
execution with checked readback is required for a hardware claim. Record
generation and revision so observations are not generalized to all AGX GPUs.

## Timing

Record the time source and its units, frequency, resolution, wrap behavior,
and synchronization boundaries. Separate CPU elapsed time, firmware command
timestamps, and any candidate shader counter. Include warmup, an empty/control
workload, repeated samples, and raw measurements. Record clocks, temperature,
or concurrent work when measurable; otherwise state that they were unavailable.

Do not infer instruction cycles from a host round trip or assume that a maximum
core frequency is the current frequency. Characterize timer-read overhead
before comparing short instruction sequences.

### Clock state (2026-10-16)

The GPU clock moves between discrete states, from about 446 MHz up to 1,398 MHz, set by the firmware. It reaches
the top state only after ~15 ms of continuous load (`novel-results/2026-10-16-commands-per-submit`) and drops within
~1 ms of idle. Sub-millisecond dispatches separated by host waits therefore land in mixed states, and "minimum over
repeats" does not fix this.

For cycle-level comparisons, run `scripts/clock_keeper.py` in the background. It submits back-to-back 6.3 ms commands
of a 64-lane delay kernel that hold the top state, and it costs at most 2 of 38 cores. Keep its commands long: every
compute command boundary in any process evicts the GPU-wide L2 (`novel-results/2026-10-16-l2-command-boundary`), and
the first keeper (0.13 ms commands) tripled L2-resident latency. Bracket every candidate with references, and report the
power source.

## Run records

Each run should contain `environment.json`, command arguments and return codes,
stdout/stderr, and a summary identifying exactly what passed. Preserve failed
runs, including the last known-good control and recovery steps if relevant.
Use scratch for builds and bulk output; copy the small evidence needed to
reproduce a finding into `results/` or its `novel-results/` folder.

## When a finding is ready

A new finding needs a reproducible hardware test, exact input and observed
output, a documented scope, and a reference to the software baseline it extends
or contradicts. Re-run the control and the changed case before promoting it.
Use [the finding template](../templates/finding.md).

## GPU hang safety

A GPU timeout costs about 0.5 s and a firmware recovery, and recoveries accumulate: after
about 44 in one boot the device wedged until reboot ([failed approaches](../notes/failed-approaches.md)).

* `scripts/gpu_safety.py` keeps a per-boot timeout budget (default 30, `AGX_HANG_BUDGET`) under
  `/scratch/apple-m2-playground/hang-budget/`. `run_drm_bitflip.py` refuses to start when the
  budget is spent and records every fault; the atomics runners record theirs.
* `run_drm_bitflip.py --prescreen-length` drops candidates whose applegpu-decoded length differs
  from the baseline's, so decode-desync hangs never reach the GPU.
* Prefer experiments whose encodings Mesa emits (checked against Mesa's `agx_pack.c` formula),
  vary inputs rather than encodings where possible, avoid backward branches (use straight-line
  code), and confirm every derived address without dereferencing it first.
* Run expected-hang candidates once, last, and only when a reboot is available.
