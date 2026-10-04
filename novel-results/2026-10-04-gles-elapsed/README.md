# Observed invalid GLES elapsed-query timing

Status: reproduced API observation on the installed Asahi stack; timer calibration
**FAIL**. This is not a new AGX instruction or microarchitecture finding.

On `/dev/dri/renderD128`, reporting `asahi` and `Apple M2 Max (G14C B1)`, GLES
3.2 Mesa 25.1.9 advertises 64-bit `GL_EXT_disjoint_timer_query`. Ten loaded elapsed
queries in each of two bounded runs returned near-2^64 nanosecond values despite
available results, zero GL errors/disjoint flags, and exact GPU compute readback.

For example, [zero-repeat dispatch](../../results/2026-10-04-gles-timing/final-run/05-elapsed-r0-s0/timing.json)
returned `18446742086639928075` ns inside a millisecond-scale host interval.
An empty elapsed query returned `1` ns; initial/final no-dispatch buffer controls
passed. A revised-source one-dispatch confirmation also reproduced the invalid
loaded result. [Independent evidence review](../../results/2026-10-04-gles-timing/review.md)
recomputed all buffers and host brackets without using the runner's oracle.

The [Khronos specification](https://registry.khronos.org/OpenGL/extensions/EXT/EXT_disjoint_timer_query.txt)
defines an elapsed interval in nanoseconds. These loaded values are incompatible
with that interval; they cannot support instruction latency or physical cycles.
Unsigned-underflow resemblance does not establish which driver/firmware operation
failed. Timestamp pairs are numerically plausible but remain uncalibrated.

Reproducer: [C probe](../../tests/gles_time.c) and
[bounded runner](../../scripts/run_gles_time.py):

```sh
python3 -B scripts/run_gles_time.py
```

Expected result on the recorded stack: checked compute outputs,
`execution_verified=true`, `timers_usable=false`, `FAIL_INVALID_TIMER`, exit **1**.
Different software may fix the symptom; absence of invalid values alone cannot
validate timing boundaries. [Full report and provenance](../../experiments/timing/gles-timer-calibration.md)
include inputs, exact recurrence, libraries, kernel, raw results and limits.
Next: independently validate command timestamps before accepting any timer or
identifying an implementation cause. No vendor source was modified.
