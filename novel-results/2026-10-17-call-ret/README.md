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
