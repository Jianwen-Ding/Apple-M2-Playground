# Measured call/return model integration

Simulator commit: `753616b` in AGX-Performance-Simulator.

Later alias probing [found `call r1` falls through after writing the link](../../novel-results/2026-10-20-call-r1/README.md). The operand-before-write implementation below is a new alias counterexample; the 386 non-alias replays remain exact. Alias correction follows separately.

The functional simulator's opt-in `AGX_EXPERIMENTAL_RET=buffer-pop2` now:

- selects the lowest active operand for both register calls and returns;
- writes the call link in every issue-active lane before masking nonmatching
  lanes, preserving inactive r1 values;
- captures each call operand before the implicit r1 write, so a source alias
  cannot be compared against the newly written link;
- preserves default refusal of register calls/returns without opt-in, empty-mask
  fallthrough and existing target bounds/alignment checks.

Hardware basis: [return winner](../../novel-results/2026-10-20-ret-winner/README.md),
[call winner/link scope](../../novel-results/2026-10-20-call-winner/README.md) and
[scattered masks](../../novel-results/2026-10-20-sparse-control/README.md).
The r1-operand alias ordering is a defensive implementation detail; explicit
`call r1` hardware validation remains a separate follow-up.

`replay.json` records the actual simulator binary/function source SHA-256 and
each retained evidence-file digest from an exact replay of **386 original
shader/input/readback cases**. The replay uses retained bytes directly, without
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

The model update does not change stop semantics. The six independently measured
conditional/partial-stop counterexamples remain explicit under
`make verify-empty-stop`. Additional return state, nested divergent calls,
more target addresses and alias forms remain separate probing work.
