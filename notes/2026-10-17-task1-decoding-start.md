# Task 1 decoding intake, 2026-10-17

Read the workspace and AGX_Probe instructions, REQUESTS.md, remaining-work list,
failed approaches, published-knowledge survey, and simulator safe-probes and
safe-07 instructions. The immediate decoding target selected is the existing
fmadd lane-offset finding. This intake made no GPU submissions and establishes
no new hardware behavior.

## Evidence checked

`make verify-alu-bitflip` passed **54/54** offline checks against retained
hardware records. The finding and evidence README still describe 50 checks.
The existing checks cover the 10-byte form, source-A lane offsets, cross-half
layout sensitivity, and the limited bit-52 operand rule.

The simulator's `rust/src/isa/table.rs` still declares fmadd32/fmadd16 as
6/8-byte instructions, with bit 15 selecting length. Its coverage catalog
still lists `fmadd_lane_offset` as a MANUAL item. Before hardware follow-up,
the decoder needs to recognize the confirmed bit-53 length extension so the
following instruction is decoded at the correct byte boundary.

## Next bounded work

1. Extract exact tested instruction bytes and layouts from the retained
   `results/2026-10-11-alu-bitflip/` records. Do not infer that every combination
   in safe-07's proposed k/width/grouping sweep was tested. In particular, the
   verifier explicitly checks k=1,3,5,7,15,16 for fp32; this is not the same list
   as the proposed k=0,1,2,4,8,15,16,31 sweep.
2. Add 10-byte decoding and offline instruction-boundary regressions, then
   replay deterministic recorded cases. Keep unknown bit-52 behavior and
   layout-dependent cross-half behavior explicit rather than assuming ordinary
   fused multiply-add semantics.
3. Build complete, terminating programs and simulate their surrounding code
   before any hardware submission. Start with one exact recorded encoding.
4. Probe source write-to-read distances 0 through 8, then inactive source lanes,
   using only established encodings. Record undefined boundary values without
   treating them as deterministic oracles.

The existing evidence compares an immediate source write with six filler
instructions; it does not establish six as the minimum safe separation.
Similarly, source-A zero fill is not a general fp32 pair/quad boundary rule.
These limits matter before using the form for PTX shuffle-plus-fma lowering.

Reports and reproducible evidence belong here; regenerable output belongs in
scratch. Consult the current GPU budget, use complete `build_main()` programs,
and stop on the first fault as specified by the task instructions.

## Owner steering

The owner subsequently selected `call` / `ret`, including the previous hang,
as the priority. The fmadd steps above are deferred. Follow the staged
`tasks/unsafe-01-call-ret.md` plan, simulator-check all surrounding programs,
and preserve and push any fault report before ending the session.
