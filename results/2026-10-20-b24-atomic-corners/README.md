# B3 / B24: device-atomic corners (2026-10-20)

Blockers B3 and B24 (items 1-4) of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. Probes are families J
and K of `AGX-Performance-Simulator/scripts/probe_atomics.py` (snapshot here), run through `probe_variants`: every
variant differs from a Mesa surrogate only in its allowed bits, the surrogate program passed its host oracle in
`agx_run` first, and each variant ran twice on the GPU. 27 variants, **0 faults, all deterministic**.
`records.json.gz` holds every record (code, input table, output, table after, firmware time).

## B3: float atomic add and NaN (answered from the 2026-10-17 records, family G)

Every float add (`op 1` + bit 45) with a NaN in memory or in the operand stores **0x7fc00000**: payload and sign are
dropped and signalling NaNs are quieted (memory 1.0 + 0x7fc12345 / 0x7f800001 / 0x7fa00000 / 0xffc00000, the same
NaNs in memory + 1.0, NaN + NaN). The simulator already models this; PTX keeps the payload, so ZLUDA documents it.
The returning 64-bit min/max returns a *changed flag*, not the old value (2026-10-17); there is no returning-old form.

## B24 results

| Item | Probe | Result |
| --- | --- | --- |
| 1 `red.add.f32` (Rt = 0) | `J_redfadd_rt0_{0,1}`: 2,048 lanes over family G's edge and rounding pairs | **identical to the returning form**: IEEE with FTZ, canonical NaN; 2,048 / 2,048 match; the destination register is not written |
| 2 u64 min/max changed flag on equality | `J_u64_equal_u5{1,3}_rt{1,0}`: source == memory on all 32 lanes | memory unchanged; flag **0** (so the flag is `new != old`) |
| 3 odd 32-bit index (address = 4 mod 8) | `J_u64_odd_u5{1,3}` | **no effect at all**: no memory word changes, flag 0. Misaligned 64-bit min/max is silently dropped; the backend must keep 8-byte alignment |
| 3 contention | `J_u64_contend_u5{1,3}`: 1,024 lanes on one pair | final value **exactly** the min / max of all 1,025 values; no other word touched |
| 3 GPR base | `J_u64_gprbase_u5{1,3}`: address in r10_r11 (At = 0) | works like the uniform base: memory exact, flags 0/1 |
| 4 ops 11-15 with bits 45-46 = 0, 1, 3 | `K_op{11..15}_u5{0,1,3}_rt1` with family D's markers | all 15 **end the SIMD group like Mesa's encoding**: the marker before lands, nothing after runs, no memory change |

Not run here: item 5 (`memory_barrier` encodings), item 6 (six-byte opcodes), item 7 (G13X, no device).
