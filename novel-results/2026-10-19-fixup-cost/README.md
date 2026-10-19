# Fix-up cycle cost: ~200 ns wall per compare in unrolled code, fetch-bound, no hidden penalty

Status: confirmed on one device (driver-reported M2 Max G14C B1; user confirms board is a MacBook M2 Max),
direct DRM, compute stage, AC power, clock keeper running. Straight-line programs
(`scripts/probe_fixup_cost.py`): prologue (constants + one operand-pair load per lane) + 64 x
fix-up core + store; control omits the core. Only recorded-safe encodings (the exact forms of
`run_drm_fcmp_fixup.py`); every program terminates in `agx_run` with host-model-exact outputs
before submission. 60 dispatches, all outputs correct, 0 faults (hang budget untouched).

## Result (firmware ns per dispatch, 32 lanes; per-fixup = (test - control) / 64)

| Variant | Control | Test median | Per fix-up |
|---|---|---|---|
| eq (15 instr) | 5,250 | 18,250 | 203 ns |
| min (15 instr) | 5,250 | 18,583 | 208 ns |
| neu (16 instr) | 5,250 | 18,125 | 201 ns |

Sample spread per cell is wide (min-max spans ~±15%: eq 16,750-20,917), i.e. clock-state noise
between dispatches despite the keeper; the medians of the three variants are indistinguishable.
The honest reading is one number: **about 200 ns per fix-up, all variants equal within noise**.

## Reading

- 200 ns for ~110 bytes of code is 1.8 ns/byte — exactly the measured instruction-fetch rate
  ([failed-approaches](../notes/failed-approaches.md): unrolled code is fetch-bound). This
  measurement is the fetch cost, not the ALU issue cost: the three variants differ by a whole
  instruction yet cost the same.
- The cost model (`agx_cost`, same programs, `--groups 1`) predicts 29.8 / 32.1 / 30.9
  cycles per fix-up (21-23 ns at top clock) — the issue/latency part only, since the model
  does not charge instruction fetch (a known general gap, cf. the inflate I-cache note).
- **No fix-up-specific model change is needed.** The sequences are ordinary recorded ALU ops;
  the model charges them at standard rates (simulator-exact, `verify-cost-model` green). The
  ~9x gap between predicted issue cost and measured unrolled wall is the fetch component,
  which applies to all straight-line code equally. For PTX lowering, budget the fix-up as
  ~15 ordinary ALU instructions plus their code bytes.

Not established: the loop-steady-state (I-cache-hot) issue cost, which would need a counted
loop with a reference chain (`run_bench.py` style) rather than unrolled repetition.

## Reproduce

`scripts/probe_fixup_cost.py hardware --n 64 --samples 15` (60 dispatches; starts and stops
the clock keeper), `offline` to gate all 4 programs in `agx_run` first;
`make verify-fixup-cost` (offline: medians, oracle-correctness and keeper status against
[results/2026-10-19-fixup-cost](../../results/2026-10-19-fixup-cost)).
