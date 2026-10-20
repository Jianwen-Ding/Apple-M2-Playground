# Call r1 writes the link and falls through instead of using its old target

Observed on M2 Max G14C B1, compute, direct DRM, AC power, 2026-10-20.
**22 variants / 66 dispatches including exact controls, zero faults, every
recovery passed.** The explicit source/link alias is a counterexample to the
initial consume-before-write implementation in simulator commit `753616b`.
The correction is integrated in `d66f359`, with all 408 original cases exact.

The winner probe normally calls through r30. Keep its code length, call PC,
link and valid callee addresses unchanged. Replace the six-byte r1 sentinel
initialization with `mov r1,r30`, then change the two-byte `call r30` to
**`call r1` (`04 02`)**. Save the global ID and every trace address before
replacing r1. The original targets point at decoded, in-program A/B callees;
the link points at the valid forward continuation.

## Hardware observations

The initial first-active-lane 0/1 cases store the fallback marker on all lanes,
never either callee marker. They complete normally, preserve all guards and
pass recovery. The simulator instead enters the old requested callee.

Eleven further variants fill existing fallback stop padding with a post-pop
r1 snapshot, keeping every target and offset fixed. Test first-active positions
0,1,2,17,31, both address assignments and a k=1/B repeat:

- Every lane active at issue has r1 = `code_offset + call_pc + 2`.
- Every initially inactive lane retains its initialized original target.
- Every lane reaches fallback; neither original callee is entered.
- The exact no-call control (`wait 0` instead of `call r1`) reaches fallback
  with **all original r1 targets intact**, demonstrating that the register
  copy works and distinguishing a no-op from the observed link write.

This is consistent with the implicit link write taking precedence over the
aliased target read. The external behavior is established; the experiment
does not uniquely identify internal pipeline ordering or prove a general
read/write rule for other opcodes. A compiler must keep an indirect call target
in a register other than r1 when it intends to call that original address.

## Participation before reconvergence

Nine additional cases insert a marker immediately after the call's wait island,
**before** the fallback pop, removing the same 16 bytes of stop padding before
callee A. Call PC, link, overall size and both callee addresses remain fixed.
Test k=0,1,17,31 with both addresses plus a k=1/B repeat. Every originally
active lane writes that marker, including lanes whose old r1 target differs;
inactive lanes do not. Thus fallback is reached with the original issue-active
mask, rather than hiding a target-based filter behind the following pop.
All nine match the refined known-op link-write/fallthrough surrogate.

The experimental simulator now applies the issue-active r1 write before
selecting/matching the explicit operand. This reproduces `call r1` fallthrough
and unchanged issue mask. Its complete original-byte replay covers **408**
call/return cases (the earlier 386 plus these 22), with 40 Rust library tests,
23 older control tests and 75 coverage cases passing. The two older suites
also pass under default settings. Stop counterexamples remain separate.

## Simulator gate and provenance

Every exact program first passes the existing simulator's original-target
hypothesis and an independent host oracle. Both uniform-call replacements and
forced-jump paths validate complete bounded paths. After the first snapshots
establish the new hypothesis, nine variants additionally run a closer known-op
surrogate: replace the six-byte call/wait/wait island with an immediate link
write in the issue-active mask and fall through. It matches the observed
full readback exactly, without changing code size or later boundaries.

A simulator match validates the stated hypothesis and surrounding code; the
recorded hardware decides that the original hypothesis is wrong. The report
keeps those predictions and the original exact counterexamples explicit. No model
guard was removed to submit the tests. The corrected simulator now replays every case exactly; ordinary r30 target
selection/link findings remain valid. Original hypotheses and source versions
remain archived.

Complete main/table outputs, guards, inputs, decoded call, source hashes,
known-op controls, firmware, kernel/memory snapshots and recovery status are
retained. No timeout or fault occurred. Archived builder versions retain the
initial and refined hypothesis provenance.

```sh
python3 -B scripts/probe_call_r1.py --first 0
python3 -B scripts/probe_call_r1.py --first 0 --hardware
python3 -B scripts/probe_call_r1_link.py --first 1 --hardware
make verify-call-r1
```

The parent winner experiment uses 32-bit valid buffer-relative targets in one
full physical SIMD group. Empty-mask aliases, scattered alias masks, nested
aliases and other register aliases remain open. [Evidence](../../results/2026-10-20-call-r1/README.md).
