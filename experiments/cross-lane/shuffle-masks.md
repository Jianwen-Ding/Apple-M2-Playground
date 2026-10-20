# Sparse-mask shuffle index hygiene and paired 64-bit payloads

Question: does the 2026-10-18 full-warp `shfl.sync` lowering remain exact under
converged sparse participation? Can two identical b32 lowerings move arbitrary
64-bit payloads without losing either half?

Hypothesis before the sweep (2026-10-20): AGX's quad-wide OR of index bits is
not execution masked. A register index written only in active lanes may retain
poison in inactive neighbours, so four shuffles alone are insufficient. Seeding
each of the four index registers with its matching constant 0..3 before
entering divergence should prevent that contamination. Immediate-index native
shuffle forms should require no such register preparation.

Use only already recorded instructions, full physical SIMD groups and a
straight-line `if_icmp` / `pop_exec` pair. Initialize source words in every lane
before divergence. Change index initialization, keeping inputs and the body
fixed. Compare all defined data outputs and arithmetic predicates against an
independent host transcription of the [PTX pseudocode](https://docs.nvidia.com/cuda/parallel-thread-execution/#data-movement-and-conversion-instructions-shfl-sync).
Reads from inactive source lanes are undefined by PTX and excluded from data
comparisons. Inactive destination sentinels, read-only input planes, guards and
the main output are checked separately. This tests converged sparse masks;
it does not implement PTX's rendezvous across divergent control paths.

The [published AGX model](https://dougallj.github.io/applegpu/docs.html#simd_shuffle)
already describes the unmasked index OR. The new hardware question is its
consequence for the proposed PTX lowering and whether initialization fixes it.

Runner: `scripts/run_drm_shfl_mask.py offline|hardware --output NEW_SCRATCH_DIR`.
Start with `--groups 5 --only control-before`, then the same small run with
`--only poison-idx-3`. Each exact program must pass its raw-AGX software oracle
and complete under `agx_run` before hardware submission. Stop on any fault,
timeout, guard failure or unexpected positive-case mismatch.
