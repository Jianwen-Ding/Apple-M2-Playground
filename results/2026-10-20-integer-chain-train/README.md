# Consecutive integer-add evidence

Nineteen gzip records retain shader/control bytes, initial and final complete
buffers, repeat indices, all firmware timestamps and wait results, completion
markers, source/binary hashes, and power/boot/memory/kernel/recovery snapshots.
There are 1,156 timed candidate submissions and 38 single-dispatch controls.
All 19 final candidate buffers and all 38 controls are exact. Intermediate
candidate buffers are not captured. No fault event occurred.

`make verify-integer-chain-train` performs no GPU work. It rebuilds each unique
program, gates full functional simulation including successive invocations,
checks independent scalar results and guards, verifies every timestamp/wait,
and checks nonoverlapping whole probe windows. It validates source archives,
harness and functional binary hashes, then predicts each timing cell using
explicit launch settings and the model's 1398 MHz assumption.

`analysis.json` binds records, model sources, binaries, calibration inputs and
the preceding isolated-study analysis. It retains all timing samples and the
early/late distributions, slopes and residuals. `source-versions/` preserves
the probe source used before the shared GPU-worker lock was added. The lock
now refuses concurrent train workers before submission.

`make test-integer-chain-train` checks lock contention and malformed harness
output using CPU-only mocks, including missing/duplicate repetitions, failed
waits, invalid timestamps, completion mismatches and partial readbacks.

[Interpretation and limits](../../novel-results/2026-10-20-integer-chain-train/README.md).
