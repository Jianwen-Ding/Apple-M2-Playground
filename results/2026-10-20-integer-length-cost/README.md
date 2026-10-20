# Program-length arithmetic evidence

Fifty gzip records retain exact shader/control bytes, inputs and complete
final buffers, guards, native configuration/stdout, every repeat/wait and
firmware/get-time timestamp, source/binary/launch bindings, kernel/memory/power
snapshots and recovery controls. All 3080 timed candidate submits and 100
controls complete. All final buffers are exact and no fault event occurred.
Intermediate candidate buffers are not captured.

`make verify-integer-length-cost` uses no GPU. It rebuilds each unique full
program, checks simulator execution against an independent scalar oracle and
successive table states, then checks every retained final and control buffer.
It validates native configuration, completion and repeat metadata, the M2 Max
device parameters, every firmware/get-time bracket, the observed 1000 us
minimum host interval, and nonoverlapping complete probe windows on one boot.

`analysis.json` binds every record and relevant source, functional/native/model
binary, calibration input and preceding gap-study analysis. The unchanged
native source and binary must match that earlier study. Exact native changes
are documented in its [source diff](../2026-10-20-integer-timing-state/native-origin.patch).
This experiment only redirects the established runner's output destinations;
its parser, watchdog, lock, native code and recovery flow are unchanged.

The analysis retains chronological ordering, every firmware sample and host/
firmware idle interval, quarter distributions, per-cell spread, program size,
explicit model predictions and adjacent candidate-time slopes. Model clock
1398 MHz is an assumption; physical frequency and per-core distribution are
not measured by these shaders. Controls validate correctness and recovery,
not a matched launch-time baseline. No timing calibration changed.

[Interpretation and limits](../../novel-results/2026-10-20-integer-length-cost/README.md).
