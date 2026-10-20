# Supplied M2 core maps reproduce retained SR20 buffers exactly

2026-10-20, host-only implementation and verification. The functional model
now accepts an optional observed core map through `agx_run --m2-core-map FILE`
or `func::run_with_m2_core_map`. All **80 retained SR20 maps** from the
[geometry corpus](../2026-10-20-integer-geometry-cost/README.md), including
72 full-size maps and eight pilots, reproduce complete hardware buffers
literally when that scheduling input is supplied. Arithmetic, tag words and
all guards match; this is no longer only a placement-property comparison.

The JSON input has one packed `(cluster<<4)|core` ID per linear workgroup,
with x varying fastest, then y, then z. Length must match checked geometry,
and each ID must be enabled by the 38-core M2 Max masks 3ff/1ff/1ff/3ff.
For 1-D full-workgroup grids at sizes 32/64/128/256, aligned blocks of eight
must remain in one cluster; a shorter final block is accepted. Other
geometries receive length and enabled-core validation without imposing that
unmeasured block rule.

Map validation precedes main execution and mapped-memory writes. The CLI
also validates before executing a preamble or producing output dumps. It
echoes `core_map: "m2"` and the number of mapped workgroups in its JSON result.
The library exposes `validate_m2_core_map` for callers that run a preamble
separately. SR20 is replaced consistently for every SIMD group and lane in
the workgroup; SR17 slots retain the existing selected mode's values.

Default CLI output and literal buffers match the archived historical model
for all **64 unique program/launch cases**, including both SR19/SR20 twins.
Three library tests additionally preserve hand-checked default and synthetic
core/slot values, verify supplied IDs across every lane and a partial tail,
reject bad input before writes, and avoid imposing 1-D blocks on 2-D geometry.
Five CLI failures cover wrong length, disabled IDs, a mixed cluster block,
negative IDs and the wrong JSON type. Invalid inputs fail before an invalid
preamble can execute and leave an existing dump untouched.

Historical and current model fingerprints are distinct. Raw hardware records
still require their exact recorded checker hash. Verification executes the
new model against independent oracles and reports its fingerprint separately;
the archived checker is used for the 64 direct default comparisons. Existing
measurements and their canonical analyses are not rewritten.

All seven earlier ordinary arithmetic regression targets also pass with the
new functional binary: 405 retained records covering 19821 previously completed
submissions. These are host-only rechecks, not new hardware dispatches.

The supplied map is explicit scheduling state. This does not predict placement,
reconstruct SR17 slots, replay concurrent execution, infer operating frequency
or calibrate timing. The existing zero-core default and synthetic stress mode
remain available. Prepared functional traces now accept this map in the
[subsequent tracing extension](../2026-10-20-observed-core-map-tracing/README.md).
The subsequent [cost-path extension](../2026-10-20-observed-core-map-cost/README.md)
accepts complete core maps with explicit wave and memory assumptions. No hardware was submitted for this change.

[Replay evidence and commands](../../results/2026-10-20-observed-core-map-replay/README.md).
