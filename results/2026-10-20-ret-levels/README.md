# Return depth transformation

21 records: the initial depth-3 exploratory return with a decrement-hypothesis
input, then actual/known-state programs for M=0..4 and rotations 0/1. The two
M=0 rotations are deliberate identical full-group baselines. Each program is
bracketed by exact original-state jump controls.

Inputs: original per-lane depth and candidate desired depth (two 32-word planes).
Outputs: prefix marker, five r0l snapshots before/after 0..4 pops, fallback
marker, then 16 untouched guards. Main output stays guarded and untouched.

The candidate state in the initial record decrements inactive depths; that
hypothesis fails. Later inputs explicitly construct `0->2,1->0,other unchanged`
using known nested IFs and jump to the same trace. Ten such hardware surrogates
match the actual returns. Original records and failed hypothesis classification
are preserved. `make verify-ret-mask-state` independently derives the measured
trace instead of trusting that historical classification.

Full source/model/harness provenance, decoded boundaries, kernel/firmware,
memory and recovery data remain in each record. No GPU is used by the verifier.
See the [finding](../../novel-results/2026-10-20-ret-mask-state/README.md).
