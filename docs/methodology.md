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
