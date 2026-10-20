# Native relative/xor/rotate shuffle liveness integration

Simulator **4dd68e9** extends the independently measured source-liveness rules
to `simd_shuffle_down`, `simd_shuffle_up`, `simd_shuffle_xor` and
`simd_shuffle_rotate_up`. Both interpreters exclude stopped low-index bits,
preserve living masked contributions and self-fallback for a stopped selected
source. Per-form quad-low rotation/xor, cross-quad selection and up/down bounds
remain intact. Underlying terminated register contents are not inferred.

Evidence is separate from the earlier plain-shuffle correction:

- [160 stopped-source programs](../../novel-results/2026-10-20-stopped-native-shuffle/README.md):
  four forms, depths 1/3, two rotations, ten offsets, paired immediate/register
  reads. 480 dispatches, all exact controls and zero faults.
- [320 index-contribution programs](../../novel-results/2026-10-20-native-dead-index-or/README.md):
  four forms, both alternating masks, all four low seeds, ten new offsets.
  960 dispatches, all exact controls and zero faults. Twenty-four cases per
  form distinguish retained from excluded stopped seed bits.

The first diagnostic case for each form and question was inspected separately
before its matrix. Every actual shader passed the explicitly recorded old
simulator hypothesis first. The original 54 source and 264 index-contribution
counterexamples, **318 total**, now replay exactly. Original evidence remains
unchanged; two original builder sources were archived by hash before updating
gates. Current builders require full measured-program equality before any
new hardware submission. Independent target verifiers still reconstruct
shader bytes, resolve recorded source hashes and check every readback word.

`model-replay.json` binds binary and source hashes plus all **1,595 original
control evidence-file digests**. It replays retained code/input bytes directly,
without regenerating a shader or submitting GPU work. Earlier return/stop,
plain-shuffle, masked-counter, alias and target-winner cases remain exact.

Validation: 42 Rust library tests pass, including both interpreter paths for
each native form, stopped-source fallback and dead seed exclusion. All 23
retained control-suite and 75 control-coverage cases pass with both default
settings and the opt-in return model. The earlier sparse-mask/paired-64-bit
shuffle verifier passes both seeds, including deliberate contamination cases.
Native source/index target verifiers and all 1,595 saved control replays pass.

Open work includes quad and other cross-lane termination effects, nested
divergent calls, deeper counters, and timing calibration. These findings do
not characterize uninitialized source data, other dispatches' registers or
terminated-lane storage.
