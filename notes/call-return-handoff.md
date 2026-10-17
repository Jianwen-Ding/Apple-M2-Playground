# Remaining G14C call/return work: agent handoff

Updated 2026-10-17. This is the current plan for the unfinished call/return
investigation. Read the [hardware finding](../novel-results/2026-10-17-call-ret/README.md)
and [hang/memory procedure](hang-memory-followup.md) first. Earlier task plans
and the early sections of the finding retain historical hypotheses, not the
current target formula or recovery policy.

## Established scope and files

Measured with one full 32-lane SIMD group on M2 Max G14C:

- Six-byte direct call: target = call PC + signed byte displacement;
  r1 = shader-buffer code offset + call PC + 6.
- Two-byte register call: uniform target = shader-buffer-relative byte address;
  r1 = shader-buffer code offset + call PC + 2.
- Return consumes a shader-buffer-relative byte address. Leave the code offset
  in the link. The default harness code offset is 0x2000.
- At the return destination, `pop_exec r0l, 2` reactivates the measured lanes.
  Two pops of one also work; intervening stores and stops remain masked.
  This is an effective mask-depth observation, not a general stack model.
- Two nested direct calls work when the outer link is saved in r29 and restored
  to r1 before the outer return. Timing is not calibrated.

The simulator's measured opt-in is `AGX_EXPERIMENTAL_RET=buffer-pop2`.
`AGX_EXPERIMENTAL_RET=1` enables a contradicted historical hypothesis and must
never gate a new hardware probe. The measured model rejects partial active
returns and partial/divergent register calls. Its empty-mask return fallthrough
is **not hardware evidence**. Uniform direct calls being accepted under a
partial mask is also not proof of hardware behavior in that scope.

Useful files in the playground:

- `scripts/probe_control_followup.py`: `roundtrip()` builds the working direct,
  indirect and nested programs; `hardware()` records controls and recovery.
- `scripts/probe_ret_landing.py`: landing-map construction and memory snapshots.
- `scripts/verify_call_ret.py`: exact evidence reconstruction, successful-model
  replays, historical failures and negative partial-mask checks.
- `results/2026-10-17-call-ret/`: historical bundles and per-case follow-ups.

Adjacent simulator files: `rust/src/func.rs` (`OpKind::Call`, `OpKind::Ret`,
`call_base()`), `scripts/coverage.py` (`gate`, `simulate`),
`scripts/coverage_catalog.py`, `scripts/probe_calls.py` (historical).
Do not use the old stage-2 builder as a ready-to-run return probe: its comments
and layout predate the measured target/mask rule.

## Coordination and preflight

One agent owns hardware submissions and the shared fault/event log at a time.
Other agents can independently prepare simulator regressions, oracles and
analysis of retained records. Agree on ownership before another hardware agent
starts; separate working directories do not isolate the physical GPU. Preserve
other agents' changes and record the simulator revision/hash used by each run.

From `/save/workspace`:

```sh
export PATH=/scratch/rust/cargo/bin:$PATH
export RUSTUP_HOME=/scratch/rust/rustup
export CARGO_HOME=/scratch/rust/cargo
cd AGX-Performance-Simulator
make rust
cd ../apple-documentation-playground
make verify-call-ret test-probe-watchdog
python3 -B scripts/gpu_safety.py status
```

Last observed event count was 3/30 on boot
`bf004820-c058-4071-bcdb-291bfbbcf55c`; read current status instead of assuming
that count or boot still applies. Check AC, available memory and shmem using
the existing snapshot helper. First run a known-good, exact full-buffer control.

## Common construction and simulator gates

Use one SIMD group initially, no barriers, no data-dependent loops and no
cross-group dependencies. Save original lane/global IDs before call clobbers
r1; index every trace by the saved ID. Save each live return link separately
before any nested call. Do not restore the ID into r1 before consuming its link.

Allocate initialized per-lane trace slots for: original mask/ID, pre-call marker,
callee identity, captured link, explicit return operand, pre-return marker,
first visible landing marker, post-reconvergence marker and final continuation.
Check every output/table word and guard, including inactive lanes. Keep unknown
forms out of the known-good recovery control.

Decode the entire assembled program and enumerate instruction boundaries.
Every candidate transfer must land on a real instruction inside that program;
even byte alignment alone does not establish an instruction boundary. Assert
the changed instruction's exact bytes, size, operand registers and allowed bit
differences. Use unique names and refuse to overwrite existing records.

For each unmodeled case, simulate a complete known-operation surrogate with an
independent oracle. Also simulate each possible callee/landing path with the
unknown transfer replaced by a known direct transfer and any required synthetic
link setup. For a two-byte transfer, reserve a six-byte island (`transfer` plus
two two-byte fillers) so a direct-jump surrogate does not shift later targets.
Recompute label offsets after final assembly, including this padding.

A surrogate validates the harness and paths, not the unknown mask/transfer
semantics. Record actual-model rejection separately. Do not remove model
guards, or claim full variant validation, simply to make a new probe pass.
Only promote semantics after exact recorded outputs support them.

## Remaining hardware cases, in dependency order

### A. Explicit return-register selection (smallest isolated uncertainty) — DONE

The initial no-call map set r1 and r30 to the same target. A probe set r1 to
landing A (0x2400) and r30 to landing B (0x2600), then executed `ret r30`.
Hardware stored MARKER_B at table words 32-63, confirming that `ret rX` uses
the explicit operand register rX, not an implicit r1 link. No fault, budget
unchanged. Evidence: `ret-r30-vs-r1.json.gz`.

### B. Partial masks and return reconvergence — direct call DONE, ret still open

Direct call under a partial mask is now measured: odd lanes active via
`if_icmp r0l, ueq, (gid & 1), 1`, callee stores link + marker. Hardware shows
link and marker on odd lanes only, 0 on even lanes; the simulator predicts
exactly this. Evidence: `partial-mask-call.json.gz`. The earlier claim that
the simulator cannot model per-lane masks was wrong: the test had loaded the
lane ID from a uniform address, so the condition was true for all lanes.
Using r1 (the harness gid) directly gives a real per-lane mask, and
`mask_ctl` sets exec from r0l as expected.

Still open: Priority C (empty masks: skipped vs issued call/ret) and beyond.
Measured 2026-10-17: the combined partial direct-call/return sequence diverges
and rejoins — active lanes round-trip through the callee while inactive lanes
run the caller post-call; evidence `partial-mask-callret.json.gz`. Ret is a
group-level transfer, not a per-lane branch — do not assume inactive lanes
continue past a bare ret.

Start with one direct call to a common callee under an `if`, without `ret`;
record which lanes receive a link and reach the callee. Use known branches to
finish. Then isolate a partial-mask `ret` to one common valid landing, and only
then attempt the combined partial direct-call/return sequence.

Use odd lanes first, then one lane, 16 contiguous lanes and 31 lanes as separate
cases. Record both selected and unselected lanes. Distinguish the caller's
existing mask depth from return's effect; do not assume `pop_exec 2` composes
with an outer `if`. Compare bounded landing layouts with explicit pop amounts
and trace where lanes first become visible. Simulator-check every such layout
and its final termination path. The prior no-pop fault is already recorded;
do not repeat it without a new question that the added markers can answer.

Test uniform register call under a partial mask only after the direct version
and return behavior are understood. Passing partial direct call does not imply
that the register form has the same scheduling rule.

### C. Empty masks: skipped instruction versus issued instruction — DONE

Measured 2026-10-17: with an empty mask, issued direct call, register call
and ret all fall through (FALL on all lanes, no transfer markers, no faults);
evidence `empty-mask-{call,callreg,ret}.json.gz`. An issued instruction under
an empty mask is a no-op — distinct from the threadgroup-atomic ending
opcodes, which end the group even with an empty mask. This also fixed a
simulator bug (empty direct calls transferred; empty register calls were
rejected); the simulator now falls through like hardware, and predicts all
three hardware outcomes exactly.

### D. Two divergent register-call targets — DONE

Measured 2026-10-17: lane 0's target wins (parity, swapped parity, and
lane-0-alone-vs-31 all agree). Only lanes addressed to lane 0's target enter
the callee (link set for those lanes only); the rest skip the call and run
the caller post-call. Both partitions reconverge (CONT2 everywhere).
Evidence: `divergent-callreg[-swap|-lane0b].json.gz`.

### E. Divergent return targets — DONE

Measured 2026-10-17: all lanes land at lane 0's target (parity, swapped, and
lane-0-alone-vs-31 all agree). Unlike calls, non-matching lanes do not fall
through — every lane executes the winning landing.
Evidence: `divergent-ret-{parity,swap,lane0b}.json.gz`.
Open refinement: lane 0 vs lowest active lane (needs lane 0 masked out).

(The original step-by-step plans for D and E are superseded by the results above.)

### F. Nested forms and code placement

Full-mask direct nesting at depth two is done. Next test direct-to-indirect and
indirect-to-direct nesting with uniform targets and separate saved links.
Then test another bounded depth with enough allocated registers. Attempt nested
partial calls only after B; do not infer a hardware return stack from a working
software-saved link sequence.

Separately move the code within the shader buffer using harness `AGX_CODE_OFF`,
and match simulator `AGX_CALL_BASE`. Extend the runner explicitly: it currently
constructs a restricted child environment and will not inherit arbitrary exported
variables. Recompute all links/targets and validate the moved layout. This tests
placement dependence; relocation across buffer objects is a different question.

### G. Cost, after functional scope is stable

Compare unrolled chains of 1, 4 and 16 full-mask call/return pairs against
matched known-branch controls, then repeat/interleave enough samples to estimate
dispatch overhead and variation. Gate every full program before hardware.
Separate direct, register-indirect and nested costs; record clocks, AC and sample
distributions. The existing single-dispatch 5,208/5,750/9,500 ns observations are
not cycles per pair. Introduce a counted loop only after the unrolled cases
match, with an independently proven trip count and simulator step bound.

## Historical out-of-program returns

The old quiet completions remain unexplained. Analyze their retained bytes,
fetch addresses, markers and mask behavior offline. Preserve their explicit
unsupported status in verifiers. Do not rerun out-of-program targets or turn
their completion into a valid-return claim. Use padded in-program diagnostic
layouts if a new hypothesis needs hardware discrimination.

## Faults, hangs and evidence

The owner's current instruction supersedes older first-fault stop wording:
log recovered faults, check recovery with an exact known-good control, and
continue only when that control passes. Do not blindly repeat a faulting case.
A persistent hang, failed control or probe process blocked after kill stops
further GPU submissions. Save and push the diagnostic record/report promptly.
Missing continuation markers with completed firmware timestamps are an outcome
to explain, not by themselves a hang.

Use `probe_control_followup.hardware()` and its bounded watchdog for new cases.
It saves code/input/phase before submitting, records memory diagnostics and
partial readback, and preserves failure evidence before attempting recovery.
Apply the linked unified-memory procedure if a hang suggests address, visibility
or allocation triggers; GPU follow-ups depend on established recovery.

## Independent offline work and completion criteria

A simulator agent can add regressions now for the measured full-mask model:
six-byte versus two-byte links, destination reconvergence, two depth-one pops,
saved outer links, uniformity checks, and rejection of invalid targets. Keep
partial/divergent forms unsupported until the hardware agent supplies records.
An analysis agent can reconstruct historical quiet returns and design independent
mask/trace oracles. Neither needs GPU access or a new hardware dispatch.

For each newly measured scope, store durable evidence in the playground:
exact code/control/inputs, decoded transfer and target map, complete readback,
firmware timestamps, kernel logs, memory snapshots, recovery result and hashes.
Add a novel-results report and an offline verifier, link it from the call finding
and coverage status, then update simulator semantics only within measured scope.
Run the call verifier, relevant retained control cases, Rust tests and any new
scope's exact replay. Report unmodeled cases explicitly. Commit and push both
affected repositories before handing work off or stopping.
