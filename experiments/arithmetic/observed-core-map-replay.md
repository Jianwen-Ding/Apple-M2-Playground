# Optional observed core-map replay

Implemented 2026-10-20. The geometry corpus provides 72 full-size end
maps with all 38 M2 Max core IDs and aligned eight-workgroup cluster blocks
at the tested 1-D shapes. Default functional simulation deliberately uses
core zero; nonzero `Dispatch::placement` is a synthetic stress mode, not a
physical M2 scheduling model. Preserve both existing behaviors.

The separate optional input is `--m2-core-map FILE`, with library entry points
`run_with_m2_core_map` and `validate_m2_core_map`. A JSON array supplies one packed
SR20 core ID per linear workgroup. Validate array length against checked
geometry and each ID against enabled M2 masks before executing or mutating
mapped memory. At the measured 1-D workgroup sizes, check the observed aligned
eight-workgroup cluster constraint, including a partial tail; do not claim it
for other geometries. A supplied map sets the workgroup's SR20 value for all
its SIMD groups. It does not specify SR17 slots, timing or concurrency.

Use the already recorded candidate bytes, inputs and observed maps to replay
literal complete outputs, with independent arithmetic/guard checks. Preserve
the original functional-binary hashes and committed baseline analysis; bind
the new replay binary separately. Default-mode regression must still match
the scalar/default-placement expectations. Historical provenance checks should
distinguish a recorded model from a newer model being tested, rather than
rewriting the raw evidence or demanding identical binary hashes across versions.

Completed: 80 observed maps reproduce complete hardware buffers literally;
64 unique default cases match both the archived model and independent oracles.
Three targeted library tests and five CLI failures pass. All evidence comes
from the existing ordinary arithmetic corpus; no hardware was submitted.
See the [finding](../../novel-results/2026-10-20-observed-core-map-replay/README.md)
and [evidence](../../results/2026-10-20-observed-core-map-replay/README.md).
