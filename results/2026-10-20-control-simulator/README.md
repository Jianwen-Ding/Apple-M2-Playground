# Measured call/return model integration

Initial simulator commit: `753616b`; alias correction: `d66f359` in AGX-Performance-Simulator.

Later alias probing [found `call r1` falls through after writing the link](../../novel-results/2026-10-20-call-r1/README.md). The original operand-before-write implementation was a new alias counterexample. Commit `d66f359` corrects it; all 408 cases now replay exactly, including 22 alias cases.

The functional simulator's opt-in `AGX_EXPERIMENTAL_RET=buffer-pop2` now:

- selects the lowest active operand for both register calls and returns;
- writes the call link in every issue-active lane before masking nonmatching
  lanes, preserving inactive r1 values;
- makes the implicit link write visible before operand selection/matching,
  reproducing `call r1` fallthrough with the issue-active mask unchanged;
- preserves default refusal of register calls/returns without opt-in, empty-mask
  fallthrough and existing target bounds/alignment checks.

Hardware basis: [return winner](../../novel-results/2026-10-20-ret-winner/README.md),
[call winner/link scope](../../novel-results/2026-10-20-call-winner/README.md) and
[scattered masks](../../novel-results/2026-10-20-sparse-control/README.md).
The initial consume-before-write alias assumption was tested separately and
contradicted by 22 exact hardware cases. The corrected ordering is supported
by both post-pop r1 values and immediate pre-pop participation checkpoints.

`replay.json` records the actual simulator binary/function source SHA-256 and
each retained evidence-file digest from an exact replay of **386 original
shader/input/readback cases**. That initial manifest remains preserved. The alias extension
[`model-replay.json`](../2026-10-20-call-r1/model-replay.json) binds the corrected
source/binary and all **408** cases. The replay uses retained bytes directly, without
regenerating the shader from a builder. `make verify-control-model` repeats it
without GPU access. The target-specific verifiers also check independent host
oracles and complete surrogate paths.

Additional validation: 40 Rust library tests pass; all 23 retained control
suite cases and all 75 control coverage cases replay exactly with both default
settings and the measured model. `make verify-call-ret` retains earlier
uniform/nested/default-rejection tests and now checks the measured lowest-active
result for the formerly unsupported synthetic call/return cases.

`source-before-model/` preserves the four exact probe-builder versions that
ran before hardware established these semantics. Their hashes match original
record provenance. The records and historical unsupported diagnostics are
unchanged. Current builders require the **actual full program** to match the
measured simulator before hardware submission; they no longer accept the old
unsupported result for this measured scope. `verify_probe_sources.py` resolves
old recorded hashes against these archived source bytes, while every shader
and input is still reconstructed and checked independently.

The initial integration left stop unchanged. The later
[return/stop correction](../2026-10-20-ret-stop-model/README.md) removes its six
conditional/partial-stop counterexamples and 45 return-arrival/depth
counterexamples. All **570** original hardware programs now replay exactly,
including three targets, call-r1 alias, direct pre-pop return reads, depths
through four and empty-issued return controls. Historical manifests and source
versions remain preserved. Nested divergent call composition, deeper counters,
masked counter reads and timing remain follow-ups.
