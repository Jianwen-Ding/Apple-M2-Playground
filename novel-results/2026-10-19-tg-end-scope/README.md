# Threadgroup ending opcode 11 ends the whole workgroup, not just the issuing group

Status: confirmed on one device (driver-reported M2 Max G14C B1; user confirms board is a MacBook M2 Max),
direct DRM, compute stage, AC power. Owner-approved unsafe session (first unsafe item in the loop):
exact bytes of the recorded single-group `tg-op11` case, issued by group 0 of a 2-group workgroup
while group 1 is live. Full hang procedure (`probe_control_followup.hardware`: pre-saved code,
watchdog, recovery control, kernel-log delta, memory diagnostics). 0 faults, 0 hang-budget used,
recovery controls exact. ``STOP'' condition for further unsafe submissions was not met (no fault),
but no further unsafe submissions are made in this turn.

## Design

64-lane workgroups (2 SIMD groups, one core), shared word 0. Group 0: atomic add +1 (Mesa op 0),
then op 11 (sub-derived, ret) in CONTROL, plain sub (op 1) in the surrogate. Group 1 delays
(32 dependent iadds), then reads shared word 0 eight times with counts. Mask discipline is the
measured partial-mask form (group 0 fully active / group 1 empty at the atomic: group-0-only
issue, group 1 skips and continues). CONTROL has a second 0x68 barrier (both groups rendezvous,
so group-1 reads happen strictly after group 0's add+sub: deterministic); TEST cannot have one
(group 0 ends first), so TEST is outcome counts. v2 adds an explicit group-1 re-assertion
(`if SR53 == 1` + marker store) that does not rely on the first pop.

## Result

| Run | Control (op1 sub) | Variant (op11) |
|---|---|---|
| v1, 128 lanes | reads all 0 then 1; ALIVE on group-0 lanes only; exact | **every output and table word stays sentinel** (no lane stored anything) |
| v2, 1024 lanes | reads all 0 then 1; ALIVE on group-0; group-1 remark markers all present | **every word stays sentinel, including the re-assertion markers** |

Firmware timestamps valid on every dispatch; kernel log empty; recovery control exact after each
variant; hang budget 0/30 throughout.

## Reading

Group 1 demonstrably works (control: reads, counts, markers all land). In the variant it stores
nothing — not even through the explicitly re-asserted path, which does not depend on the first
pop (and pop-under-empty-mask is independently measured to restore: `probe_pop_empty`, 32/32
markers on both groups). A group merely masked off would still hit the second barrier or store
through re-assertion; instead nothing downstream of op 11 executes in either group while the
dispatch completes cleanly with no fault. **Op 11 ends the whole workgroup, not just the issuing
SIMD group.** (Strictly measured for op 11; ops 12-15 share the family behavior single-group and
are likely the same scope — not measured cross-group.)

## For PTX / ZLUDA

- Never lower a block-scope atomic to an ending opcode while any group of the workgroup is still
  live (e.g. early-exit reductions). The safe Mesa ops 0-10 (including with return) remain the
  only choice, with explicit barriers for visibility ([tg-litmus](../2026-10-18-tg-litmus/README.md):
  no fence needed between threadgroup accesses of one workgroup).
- The simulator keeps rejecting op 11+ cross-group paths (unmodelled scope); single-group ending
  behavior is unchanged.

## Reproduce

`scripts/probe_tg_end_visible.py offline [--remark] [--lanes N]` (agx_run gates: control exact,
surrogate structural); `hardware [--lanes N] [--repeats R] [--remark]` (one workgroup-ending
case per invocation through the watchdog harness; stops at the first halt);
`scripts/probe_pop_empty.py offline|hardware` (the pop-under-empty-mask control);
`make verify-tg-end-scope` (offline, against
[results/2026-10-19-tg-end-visible](../../results/2026-10-19-tg-end-visible)).
v1 used 128 lanes (2 workgroups), v2 1024 lanes (16 workgroups); each ran once with exact
recovery.
