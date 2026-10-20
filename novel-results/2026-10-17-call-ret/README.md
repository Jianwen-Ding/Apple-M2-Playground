# Uniform direct, indirect and nested calls return through pop_exec 2

Status: uniform 32-lane call/return sequences now work on G14C; see the final
section for the measured target and mask rule. Earlier diagnostic records and
failures below are retained as historical evidence. Partial/divergent lanes
and out-of-program behavior remain unresolved.

The current [agent handoff](../../notes/call-return-handoff.md) lists remaining
cases, dependencies, simulator gates and the owner's updated fault/hang policy.
Use it instead of the historical next-work suggestions below.

## Earlier evidence, now preserved

Six previous scratch records are bundled in
[records.json.gz](../../results/2026-10-17-call-ret/records.json.gz).
C1a/C1b/C1c establish the direct six-byte call's relative jump and r1 link
(`0x2000 + next instruction byte offset`) for their all-active launches.
C2a returned through the raw link and faulted. C2b/C2c subtracted 0x2000;
these completed without running the continuation predicted by the simulator.
The old fault address is known only from the task plan, not an original log.

## New diagnostic probes (2026-10-17)

Both programs use one 32-lane group, 64 register halves, no call, no loop,
and no barrier. A marker and the operand are stored before `ret r30` at byte
512. r1 and r30 contain the same operand, so these probes cannot distinguish
an explicit r30 target from an implicit r1 target. Distinct forward landing
blocks store markers then stop. Padding between blocks is `stop` instructions.
The harness places code at shader-buffer offset 0x2000.

| Probe | Operand | Landing byte offsets from code start | Observation |
|---|---:|---|---|
| R1-map | 1024 | 1024, 1536, 2048, 2560 | Pre-return marker and operand landed in all lanes; no landing or fallthrough marker. 53,209 ns; controls 14,000 / 13,750 ns. No logged fault. |
| R1-halfword-map | 4608 (0x1200) | 1024, 4608, 5120, 9216, 9728 | Pre-control passed; variant returned zero firmware timestamps. Kernel timeout with unmapped UL1C read at **0x1000008100**, VM slot 0xd. No further dispatch submitted. |

The second operand included a test of the hypothesis that the operand is a
buffer-relative halfword address: `(0x2000 + 1024) / 2`. Other landing blocks
cover code-relative byte/halfword and current-PC-relative byte/halfword
interpretations. The fault does **not** identify the target formula: the fault
address may be a later fetch rather than the first destination. No model is
promoted from these observations.

### Simulator validation and its limit

Before each hardware run, `agx_run` executed the complete program with the
two-byte return replaced by `wait 0`; all output guards and table words matched
an independent oracle. Separate six-byte direct-jump substitutions for the
`ret; wait; wait` island tested every candidate landing block with the same
surrounding code and exact output/table comparison (4 and 5 landing paths).
All three prior direct-call probes also passed their existing simulator gates.

The actual return program was required to fail simulation with an explicit
"ret semantics unresolved" diagnostic. The old code-relative return model
contradicts retained hardware observations and is now disabled by default in
the simulator (commit `eef0074`). `AGX_EXPERIMENTAL_RET=1` enables that old
hypothesis for offline study only. A surrogate gate validates surrounding
code, **not** the unknown instruction's control transfer. The second hardware
fault demonstrates this limitation.

### Failure handling

Stopped at the first fault, without submitting a post-fault control or another
probe. Current boot budget increased from 0 to 1 of 30. The kernel reported
"Attempting recovery"; recovery was not verified with another GPU dispatch.
Exact code, pre-control output, simulator gate results, failure text, budget,
power status and kernel-log delta are in
[landing-records.json.gz](../../results/2026-10-17-call-ret/landing-records.json.gz).
The [verbatim fault log](../../results/2026-10-17-call-ret/R1-halfword-kernel-log.txt)
and failed harness binary files are retained separately. Failed-dispatch
readback is partial/untrusted and is not used as a semantic oracle.

The shmem snapshot immediately after each run was 1,769,472 bytes; it returned
to zero before the second probe. This does not establish a persistent leak.

## Reproducer and next work

`scripts/probe_ret_landing.py` defaults to simulator-only validation;
`--halfword-map` selects the second layout. `--hardware` explicitly submits
that layout with controls and stops on a failure. Do not rerun the faulting
layout blindly. These are diagnostic observations, not a safe backend lowering.

Further work should first inspect the retained encoding and complete decode,
including register selection, implicit execution-mask state, and any landing
outside the tested hypotheses. Keep return unsupported until a model explains
the quiet completions as well as the faults. Indirect calls, nesting, and
call/return timing were not attempted. Continue to inline PTX device functions.

Offline verification: `make verify-call-ret` rebuilds both exact probe binaries,
checks all simulator landing paths and default return rejection, replays all
three old direct calls, and checks the retained quiet/fault outcomes.

## Resumed investigation: recovered faults are logged and probing continues

The owner clarified that recovered faults should not end the investigation;
a failed known-good recovery control should. The earlier R1-halfword fault's
recovery was verified by an exact, simulator-checked control (14,250 ns).
`scripts/probe_control_followup.py` retains full stdout/stderr, readback,
kernel-log deltas and a post-dispatch recovery control for each new case.

Initial follow-up: `ret-pop1` and `ret-r1-pop1` with operand 1024 reached no
marker. With operand 0x2400 and pop_exec 1 at each landing, marker 1536 was
stored. Moving ret from byte 512 to 768 still stored 1536; changing the operand
to 0x2500 still stored 1536. These are observations, not a target formula.
Removing pop_exec (`ret-byte-nopop`) faulted at unmapped UL1C 0x1000008100.
Its post-control passed after two seconds; boot budget became 2/30.
All fallthrough and candidate landing paths passed simulator/oracle checks
before hardware; actual ret was rejected as unresolved. The follow-up records
are under `results/2026-10-17-call-ret/followup/`.

## Working uniform call / return sequence

Later probes established a working sequence on 32 active lanes:

- `ret rX` uses the **shader-buffer-relative byte address** in rX. The code
  offset (0x2000 in this harness) must remain in the link.
- Return leaves the lanes masked with an effective depth of **2**. At the
  destination, `pop_exec r0l, 2` makes them active. Two `pop_exec ..., 1`
  operations also work, but the intervening stores and stops do not execute.
  This is why the first visible marker was misleadingly at 1536 rather than
  the target 1024. Moving the return instruction did not move that marker.
- A six-byte direct call and return now complete, recording the callee marker,
  caller continuation and unchanged link on every lane (`call-ret-pop2`).
- A two-byte `call r30` with a uniform buffer-relative target also completes;
  its link is **0x2000 + call byte offset + 2**, not +6 (`callreg-ret-pop2`).
- Two nested direct calls complete when the caller saves r1 in r29 and restores
  it before its own return (`call-nested-pop2`).

## Explicit return-register selection (2026-10-17)

**`ret rX` uses the explicit operand register rX, not an implicit r1 link.**

Probe design: set r1 to landing A (buffer-relative 0x2400) and r30 to landing B
(buffer-relative 0x2600). Each landing has `pop_exec r0l, 2` followed by a
distinct marker stored to the table. Execute `ret r30`.

- Hardware result: MARKER_B (0xCCCC0001) stored at table words 32-63.
  MARKER_A not stored. This confirms the explicit operand register is used.
- The simulator's `AGX_EXPERIMENTAL_RET=buffer-pop2` model already uses the
  explicit operand, so the hardware matches the model.
- Control dispatch (direct store of MARKER_B) passed before and after.
- No fault, no hang, budget unchanged (3/30), kernel log clean.
- Firmware time: 11,542 ns.

This resolves the r1/r30 ambiguity from the earlier no-call landing map, where
both registers were set to the same target. The result is consistent with the
working call/return sequence (where r1 is both the explicit operand and the
link, so the distinction was invisible).

Evidence: [ret-r30-vs-r1.json.gz](../../results/2026-10-17-call-ret/ret-r30-vs-r1.json.gz).
Reproducer: `scripts/probe_ret_reg_select.py offline` (simulator) or `hardware`
(GPU submission).

## Partial-mask direct call (2026-10-17)

**A direct call under a partial exec mask transfers only the active lanes;
the callee executes only for those lanes.**

Probe design: r1 is the harness lane gid. Save it to r29, derive store
indices (table[gid] for the link, table[32+gid] for the marker), clobber r1
with SENTINEL, then `if_icmp r0l, ueq, (r29 & 1), 1` so odd lanes are active.
`jmp_exec_none` skips the call when no lane is active (safety gate). The
callee stores r1 and MARKER, then stops; it never returns.

- Hardware result: table[0:32] holds the link on odd lanes and 0 on even
  lanes; table[32:64] holds MARKER on odd lanes and 0 on even lanes.
  Inactive lanes never execute the callee stores, so no SENTINEL is visible.
- The simulator (default mode, call is modelled) predicts exactly this
  pattern, so the hardware matches the model.
- Control dispatch (all-active call) passed before and after.
- No fault, no hang, budget unchanged (3/30), kernel log clean.
- Firmware time: 8,834 ns.

This answers the first half of handoff Priority B: the call honors the
incoming exec mask, and the callee inherits it. Partial-mask `ret`,
empty-mask cases, and divergent targets remain open.

Evidence: [partial-mask-call.json.gz](../../results/2026-10-17-call-ret/partial-mask-call.json.gz).
Reproducer: `scripts/probe_partial_mask.py offline` (simulator) or `hardware`
(GPU submission).

## Partial-mask ret (2026-10-17)

**Active lanes ret normally; inactive lanes store nothing (no fallthrough).**

Probe design: odd lanes active via `if_icmp r0l, ueq, (gid & 1), 1`, then
`ret r30` to landing B (pop_exec 2 + MARKER_B). Inactive lanes should skip
the ret, hit `pop_exec r0l, 1`, and store MARKER_FALL in the same per-lane
slot. `jmp_exec_none` over the ret island is a safety gate for the empty-mask
case. Jump and wait surrogates validate the B path and the fallthrough path
independently under simulation; the simulator rejects the partial-mask ret
itself as unmodelled, as required.

- Hardware result: table[32+gid] holds MARKER_B on odd lanes and 0 on even
  lanes. Even lanes executed neither the B store nor the FALL store.
- The dispatch completes normally (firmware timestamps written, no fault).
- Control dispatch (all-active ret to B) passed before and after.
- No fault, no hang, budget unchanged (3/30), kernel log clean.
- Firmware time: 11,416 ns.

Interpretation: `ret` under a partial mask is not a per-lane branch. Active
lanes transfer to the target; inactive lanes do not continue past the ret to
the fallthrough — they are dropped (at least observably: no stores). This is
consistent with ret being a group-level reconvergence operation. Confirmed
across four masks 2026-10-17 (odd 16 lanes, single lane 0, contiguous 0-15,
lanes 0-30): active lanes store MARKER_B, inactive lanes store nothing, no
FALL marker anywhere, all dispatches complete normally with passing controls.

Refinement (same day, [ret mask-depth probes](#ret-mask-depth-rule-2026-10-17)):
the inactive lanes are not dropped — they are dragged to the landing with
their r0l unchanged (depth 1), while lanes active at issue get r0l = 2. The
earlier probes' landings began with `pop_exec r0l, 2`, which reactivates
depth-1 lanes but leaves depth-2 lanes masked through the first store —
that is why inactive lanes appeared to store nothing.

Evidence: [partial-mask-ret.json.gz](../../results/2026-10-17-call-ret/partial-mask-ret.json.gz),
[partial-mask-ret-single0.json.gz](../../results/2026-10-17-call-ret/partial-mask-ret-single0.json.gz),
[partial-mask-ret-contig16.json.gz](../../results/2026-10-17-call-ret/partial-mask-ret-contig16.json.gz),
[partial-mask-ret-lanes31.json.gz](../../results/2026-10-17-call-ret/partial-mask-ret-lanes31.json.gz).
Reproducer: `scripts/probe_partial_ret.py offline` (simulator/surrogates) or
`hardware [--mask odd|single0|contig16|lanes31|all]` (GPU submission).

## Combined partial-mask call + return (2026-10-17)

**Lanes truly diverge and rejoin: active lanes round-trip through the callee
while inactive lanes run the caller post-call, then all reconverge.**

Probe design: odd lanes active. `call` → callee stores link + CALLEE marker,
`ret r1` back to the caller post-call, which pops twice with a store after
each pop (CONT1 into table[64+gid], CONT2 into table[96+gid]). The
pre-marker survives on inactive lanes in the link slot.

- Hardware result: link + CALLEE on odd lanes; CONT1 on even lanes only;
  CONT2 on all lanes. Matches the divergence oracle byte-for-byte.
- The dispatch completes normally; controls pass before and after.
- No fault, no hang, budget unchanged (3/30), kernel log clean.
- Firmware time: 8,958 ns.

This answers the combined-sequence question: the machine supports real
per-lane divergence across call/ret, with reconvergence in the caller via
pops. (The earlier partial-ret finding — inactive lanes dropped with no
fallthrough — applies to a bare ret with no caller continuation path; here
the inactive lanes never enter the callee and proceed down the caller path.)

Evidence: [partial-mask-callret.json.gz](../../results/2026-10-17-call-ret/partial-mask-callret.json.gz).
Reproducer: `scripts/probe_partial_callret.py offline` (simulator/surrogates)
or `hardware` (GPU submission).

## Empty-mask call / ret: issued instructions fall through (2026-10-17)

**With no active lanes, an issued direct call, register call, or ret is a
no-op: the group falls through to the next instruction.**

Probe design: `if_icmp` false for every lane (gid < 0), then issue the
instruction directly (no `jmp_exec_none` skip). All register operands hold
valid in-program addresses on every lane, including inactive ones. The
fallthrough block pops and stores FALL; the callee/landing blocks pop and
store their own markers. One unknown per dispatch, with passing all-active
controls before and after.

- Hardware result, all three cases: FALL on all 32 lanes; no callee/landing
  markers; pre-marker survives in the link slot. Dispatches complete
  normally with no fault.
- No fault, no hang, budget unchanged (3/30), kernel log clean.

This also fixed a simulator bug: the simulator unconditionally transferred
empty-mask direct calls (and rejected empty-mask register calls). It now
falls through without transferring or writing the link, mirroring the
existing empty-mask ret path. After the fix the simulator predicts the
hardware outcome exactly for all three cases.

Evidence: [empty-mask-call.json.gz](../../results/2026-10-17-call-ret/empty-mask-call.json.gz),
[empty-mask-callreg.json.gz](../../results/2026-10-17-call-ret/empty-mask-callreg.json.gz),
[empty-mask-ret.json.gz](../../results/2026-10-17-call-ret/empty-mask-ret.json.gz).
Simulator fix: AGX-Performance-Simulator `rust/src/func.rs` (`OpKind::Call`
empty-mask fallthrough).
Reproducer: `scripts/probe_empty_mask.py offline` (simulator/surrogates) or
`hardware [--case call|callreg|ret|all]` (GPU submission).

## Ret mask-depth rule (2026-10-17)

**`ret` sets r0l = 2 on lanes active at issue and leaves inactive lanes'
r0l unchanged; every lane transfers to the winning target. Reconverge with
`pop_exec r0l, 2` — it handles every depth combination.**

Probes: partial-mask uniform ret (odd lanes active), and lane-0-masked
divergent ret (lane 0 -> A, lanes 1..31 -> B). Both landings carry
pop1/M1/pop2/M2/stop, and a FALL path catches any fallthrough (never taken).

- Partial-uniform: even (inactive-at-ret) lanes store M1 + M2; odd (active)
  lanes store M2 only. So active lanes need 2 pops, dragged lanes need 1.
- Lane-0-masked divergent: all 32 lanes land at B — the lowest *active*
  lane's target wins over masked-out lane 0. Lane 0 alone stores B1
  (dragged, depth 1); lanes 1..31 store B2 only (active at issue, depth 2).
- FALL never appears: dragged lanes transfer, they do not fall through.
- All dispatches complete normally; controls pass before and after.
- No fault, no hang, budget unchanged (3/30), kernel log clean.

This unifies every ret observation: full-mask uniform ret (depth 2
everywhere), partial-mask ret (active 2 / dragged 1), divergent ret
(winner = lane 0 if active else lowest active lane), empty-mask ret
(no active lanes: no transfer, no r0l change, falls through). A single
`pop_exec r0l, 2` at the landing reconverges all cases.

Evidence: [ret-depth-partial-uniform.json.gz](../../results/2026-10-17-call-ret/ret-depth-partial-uniform.json.gz),
[ret-depth-lane0out.json.gz](../../results/2026-10-17-call-ret/ret-depth-lane0out.json.gz).
Reproducer: `scripts/probe_ret_depth.py offline` (simulator/surrogates) or
`hardware [--case partial-uniform|lane0out|all]` (GPU submission).

## Mixed direct/indirect nesting and code placement (2026-10-17)

**Depth-2 mixed nesting round-trips exactly; code placement does not matter.**

- Direct→indirect: outer direct call, outer callee saves the outer link to
  r29, inner register call, inner callee stores its link + IN marker and
  returns; outer callee pops (inner ret leaves depth 2), restores r1, returns;
  caller pops twice and stores CONT. Hardware matches the simulator
  byte-for-byte, including both link values.
- Indirect→direct: mirror image, also exact.
- Code placement: the uniform direct round trip at USC offset 0x2100 behaves
  identically to 0x2000; every link shifts by exactly +0x100. Links are
  buffer-relative (base + code offset + instruction length).
- All dispatches complete normally; no fault, no hang, budget unchanged
  (3/30), kernel log clean.

The inner-ret-then-pop ordering matters: without the pop after the inner
return, the outer callee's restore/return is skipped (lanes still masked)
and the program runs off its end — caught in simulation before hardware.

Evidence: [nested-d2i.json.gz](../../results/2026-10-17-call-ret/nested-d2i.json.gz),
[nested-i2d.json.gz](../../results/2026-10-17-call-ret/nested-i2d.json.gz),
[code-placement-2100.json.gz](../../results/2026-10-17-call-ret/code-placement-2100.json.gz).
Reproducers: `scripts/probe_nested.py`, `scripts/probe_placement.py`
offline (simulator) or `hardware` (GPU submission).

## Call/ret pair cost, bounded (2026-10-17)

**A call/ret pair costs on the order of tens of ns steady-state; first-pair
and per-dispatch fixed effects dominate short chains.**

Unrolled chains of N call/ret pairs through one shared callee vs matched
jump-pair controls (jump over filler + same stores), N = 1/4/16 direct and
N = 4 indirect, 5 interleaved samples each with a background clock keeper
(keeper started/stopped cleanly). Per-pair delta = (call + ret) − jmp:

| config | variant median | control median | per-pair delta |
|---|---|---|---|
| N=1 direct | 6,166 ns | 5,000 ns | 1,166 ns |
| N=4 direct | 7,166 ns | 6,583 ns | 146 ns |
| N=16 direct | 11,875 ns | 11,458 ns | 26 ns |
| N=4 indirect | 7,291 ns | 6,959 ns | 83 ns |

Sample spreads are wide relative to the deltas (clock states even with the
keeper); firmware ns, not calibrated cycles. Exact-oracle passes on every
sample; no fault, no hang, budget unchanged (3/30).

Evidence: [callret-cost.json.gz](../../results/2026-10-17-call-ret/callret-cost.json.gz).
Reproducer: `scripts/probe_cost.py offline` (simulator) or `hardware`
(GPU submission, starts its own keeper).

## Divergent register calls: lane 0's target wins (2026-10-17)

**With per-lane call targets, the group transfers to lane 0's target; only
lanes addressed to that target participate, the rest fall through.**

Probe design: r30 = A for even lanes, B for odd lanes (then swapped, then
lane 0 → B alone vs 1..31 → A). Each callee stores the link + its marker and
returns to a common continuation that pops twice with a store after each pop.

- Even→A / odd→B: link + MARK_A on even lanes; CONT1 on odd lanes; CONT2 all.
- Even→B / odd→A: link + MARK_B on even lanes; CONT1 on odd lanes; CONT2 all.
- Lane 0→B / rest→A (1-vs-31): link + MARK_B on lane 0 only; CONT1 on
  lanes 1..31; CONT2 all.
- All dispatches complete normally; controls pass before and after.
- No fault, no hang, budget unchanged (3/30), kernel log clean.

So it is lane 0's target that wins, not the majority and not a fixed
callee: only lanes whose r30 matches lane 0's r30 enter the callee (link set
for those lanes only); the rest skip the call and run the caller post-call
directly. Both partitions reconverge (CONT2 everywhere).

Evidence: [divergent-callreg.json.gz](../../results/2026-10-17-call-ret/divergent-callreg.json.gz),
[divergent-callreg-swap.json.gz](../../results/2026-10-17-call-ret/divergent-callreg-swap.json.gz),
[divergent-callreg-lane0b.json.gz](../../results/2026-10-17-call-ret/divergent-callreg-lane0b.json.gz).
Reproducer: `scripts/probe_divergent_call.py offline` (simulator/surrogates)
or `hardware [--swap] [--lane0b]` (GPU submission).

## Divergent returns: all lanes take lane 0's target (2026-10-17)

**With per-lane return targets, every lane lands at lane 0's target.**

Probe design: no call; r30 = A/B per lane (parity, swapped, lane-0-alone).
Each landing pops twice, stores its marker, and stops.

- Even→A / odd→B: MARK_A on all 32 lanes.
- Even→B / odd→A: MARK_B on all 32 lanes.
- Lane 0→B / rest→A: MARK_B on all 32 lanes.
- All dispatches complete normally; uniform controls pass before and after.
- No fault, no hang, budget unchanged (3/30), kernel log clean.

Unlike calls (where non-matching lanes fall through), a divergent ret drags
every lane to the winning landing. Resolved same day ([ret mask-depth probes](#ret-mask-depth-rule-2026-10-17)):
with lane 0 masked out, all 32 lanes land at the lowest *active* lane's
target. Winner rule: lane 0 if active, else lowest active lane.

Evidence: [divergent-ret-parity.json.gz](../../results/2026-10-17-call-ret/divergent-ret-parity.json.gz),
[divergent-ret-swap.json.gz](../../results/2026-10-17-call-ret/divergent-ret-swap.json.gz),
[divergent-ret-lane0b.json.gz](../../results/2026-10-17-call-ret/divergent-ret-lane0b.json.gz).
Reproducer: `scripts/probe_divergent_ret.py offline` (simulator/surrogates)
or `hardware [--case parity|swap|lane0b|all]` (GPU submission).

The first successful round trip took 5,208 ns, indirect 5,750 ns, nested 9,500 ns.
These isolated firmware times are observations, not a calibrated instruction
cost. All had passing before/after controls and no fault.

The simulator's opt-in `AGX_EXPERIMENTAL_RET=buffer-pop2` reproduces every word
of the seven successful in-program follow-up records, including indirect and
nested calls. It rejects out-of-program targets and a return without
reconvergence that runs off the program. Default execution still rejects ret
and register calls; divergent/partial-lane return state and the quiet
out-of-program completions remain unmodelled. The old opt-in value `1` is the
contradicted historical hypothesis and must not be used to gate hardware.

Validation after the model update: 31 Rust library tests pass. All 23 retained
control-flow tests and all 75 coverage control-flow cases replay exactly both
with default settings and with `AGX_EXPERIMENTAL_RET=buffer-pop2`. The playground
verifier additionally rejects synthetic partial-lane direct-return and indirect
call probes; those negative tests make no new hardware claim. The initial
post-fault recovery control is retained in `results/2026-10-17-call-ret/recovery-control.json.gz`.

## Current model: clamping pop, uniform ret, stop padding (2026-10-17, supersedes earlier mask-depth notes)

**Qualification from isolated hardware probes (2026-10-20):** the empty-stop
depth-1 kill rule below fits return-context records, but fails when equivalent
pop-reactivation patterns are constructed with conditionals. A partial active
stop also leaves masked lanes able to resume. The simulator is unchanged and
the [new evidence](../2026-10-20-empty-stop/README.md) retains six exact
counterexamples; do not generalize the old stop heuristic outside its measured
return scope.

Earlier sections in this file describe intermediate models (no-op pop underflow,
"dragged lanes reactivate on divergent ret") that were fitted to probes that had
bugs. They are kept for history; this section is the current reading.

- `pop_exec r0l, n` is clamping subtraction: `r0l = max(r0l - n, 0)`.
  Evidence: [pop-semantics.json.gz](../../results/2026-10-17-call-ret/pop-semantics.json.gz)
  (odd lanes active, even masked; both `pop_exec 1` and `pop_exec 2` reactivate all 32 lanes).
  The earlier record [pop-semantics-postmask-r21-bug.json.gz](../../results/2026-10-17-call-ret/pop-semantics-postmask-r21-bug.json.gz)
  is invalid: its index register was set after the mask.
- `ret rX` on an active mask: all active lanes get `r0l = 2` and leave the active set;
  inactive lanes keep their `r0l`. Target is the agreed `rX`, or lane 0's `rX` when lanes
  disagree and lane 0 is active. Divergent with lane 0 inactive is still unmodelled.
- Empty active mask: call and ret fall through.
- `stop` with no active lane, reached while some lane is at depth 2, kills lanes at depth 1
  (modelled as `r0l = 0xffff`). This is the only special case and is not yet hardware-confirmed.
- Divergent direct-target `call rX`: lane 0's target wins; matching lanes stay active and get the link.

With this model every retained record that has a `variant` reproduces word-for-word in
`AGX_EXPERIMENTAL_RET=buffer-pop2` (audit run 2026-10-17 across all 28 call/ret variant
records, including `nested-partial`). Records whose labels came from the old model carry an
`interpretation_note` with the previous label.

Invalid or corrected records:
- `partial-mask-ret*-site-bug.json.gz`: the probe jumped to `0x2000 + landing` without the
  code site offset, so ret landed in stop padding. Not evidence about the landing; kept only for audit.
- Fixed probe `scripts/probe_partial_ret.py` (uses `0x2000 + site + landing`) re-ran on hardware
  for masks `odd`, `single0`, `contig16`, `lanes31`. All four store B on all 32 lanes, FALL nowhere.
  This is the clamping prediction, not a masked-ret result.

Open items for the next session:
- Confirm the `stop` special case with a checkpointed probe that stores `r0l` before and after the padding.
- Divergent ret with lane 0 inactive remains unmodelled.
- Refresh the stale `interpretation` labels in the remaining records (done for the ones listed above).
