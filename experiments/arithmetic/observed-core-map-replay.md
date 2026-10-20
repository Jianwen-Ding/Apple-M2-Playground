# Next implementation: optional observed core-map replay

Proposed, not implemented yet. The geometry corpus provides 72 full-size end
maps with all 38 M2 Max core IDs and aligned eight-workgroup cluster blocks
at the tested 1-D shapes. Default functional simulation deliberately uses
core zero; nonzero `Dispatch::placement` is a synthetic stress mode, not a
physical M2 scheduling model. Preserve both existing behaviors.

Add a separate optional input, tentatively `--m2-core-map FILE` and a library
entry point such as `run_with_m2_core_map`. A JSON array supplies one packed
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

CPU tests should reject a wrong map length, disabled core IDs and a mixed
cluster block before any writes, and cover whole and partial blocks. Replay
several seeds/maps and confirm the default and synthetic modes are unchanged.
All evidence can come from the existing ordinary arithmetic corpus; no new
hardware or excluded-family experiments are needed for this implementation.
