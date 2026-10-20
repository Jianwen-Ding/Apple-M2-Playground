# Remaining G14C call/return work: agent handoff

Updated 2026-10-17. This is the current plan for the unfinished call/return
investigation. Read the [hardware finding](../novel-results/2026-10-17-call-ret/README.md)
and [hang/memory procedure](hang-memory-followup.md) first. Earlier task plans
and the early sections of the finding retain historical hypotheses, not the
current target formula or recovery policy.

2026-10-20 follow-up: [isolated stop probes](../novel-results/2026-10-20-empty-stop/README.md)
confirm the old stop heuristic in return context and contradict it for masks
constructed only from conditionals. Partial stops terminate issuing lanes
while masked lanes resume. `make verify-empty-stop` preserves 17 exact variants,
including six known simulator counterexamples. A qualified model and the
additional return state remain open; no simulator semantics were changed.

The subsequent [divergent-ret winner matrix](../novel-results/2026-10-20-ret-winner/README.md)
tests genuine disagreement among active lanes with lane 0 excluded. Every
first-active lane 1..31 and both target assignments select the lowest active
lane's target (64 variants / 192 dispatches, no faults). Scattered masks and
the simulator winner extension remain open; `make verify-ret-winner` retains
the actual model rejection and checks both landing surrogates separately.

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

### B. Partial masks and return reconvergence — DONE (unified mask-depth rule)

Direct call under a partial mask: odd lanes active, callee stores link +
marker on odd lanes only. Partial ret: unified rule now measured — ret sets
r0l = 2 on lanes active at issue and leaves inactive lanes' r0l unchanged;
every lane transfers to the winning target (no fallthrough ever). Landing
pop1/M1/pop2/M2 discriminates depth: active lanes skip M1 (need 2 pops),
dragged lanes store M1 (need 1 pop). A single `pop_exec r0l, 2` reconverges
all cases. Evidence: `partial-mask-call.json.gz`, `partial-mask-ret*.json.gz`,
`partial-mask-callret.json.gz`, `ret-depth-*.json.gz`.

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

Measured 2026-10-17: all lanes land at the winning target (parity, swapped,
and lane-0-alone-vs-31 all agree). Unlike calls, non-matching lanes do not fall
through — every lane executes the winning landing. Winner rule resolved same
day (ret-depth lane0out): lane 0 if active, else lowest active lane.
Evidence: `divergent-ret-{parity,swap,lane0b}.json.gz`, `ret-depth-lane0out.json.gz`.

(The original step-by-step plans for D and E are superseded by the results above.)

### F. Nested forms and code placement — DONE

Measured 2026-10-17, all uniform and simulator-exact on hardware:
- Direct→indirect and indirect→direct nesting at depth 2 (outer link saved
  to r29 across the inner call and restored before the outer return). Both
  round trips match the simulator byte-for-byte, no faults.
  Evidence: `nested-d2i.json.gz`, `nested-i2d.json.gz`.
- Code placement: the uniform direct round trip runs identically with the
  code blob at USC offset 0x2100 instead of 0x2000 (AGX_CODE_OFF=0x2100,
  simulator AGX_CALL_BASE=0x2100). Links shift by exactly +0x100, proving
  links are buffer-relative (base + code offset + len) and calls/returns
  are placement-independent.
  Evidence: `code-placement-2100.json.gz`.
Reproducers: `scripts/probe_nested.py`, `scripts/probe_placement.py`.

Separately move the code within the shader buffer using harness `AGX_CODE_OFF`,
and match simulator `AGX_CALL_BASE`. Extend the runner explicitly: it currently
constructs a restricted child environment and will not inherit arbitrary exported
variables. Recompute all links/targets and validate the moved layout. This tests
placement dependence; relocation across buffer objects is a different question.

### G. Cost: bounded unrolled measurement — DONE (order of magnitude)

Measured 2026-10-17 with a background clock keeper (started/stopped cleanly),
5 interleaved samples per program, all simulator-gated, all exact-oracle
passes. Per-pair delta = (call + ret + stores) − (jmp + filler + stores):

- N=1 direct: 1,166 ns/pair (dominated by per-dispatch fixed/cold effects).
- N=4 direct: 146 ns/pair. N=4 indirect: 83 ns/pair (same order; noisy).
- N=16 direct: 26 ns/pair (best steady-state read).
- Distributions overlap substantially (e.g. N=16 variant 11.6–15.7 µs vs
  control 10.6–12.8 µs); firmware ns, not calibrated cycles.

The pair cost is on the order of tens of ns steady-state; first-pair/cold
effects dominate short chains. Precise cycle decomposition (in-dispatch CPU
timer + reference chain, counted loops with proven trip counts) remains open.
Evidence: `callret-cost.json.gz`.
Reproducer: `scripts/probe_cost.py offline` or `hardware`.

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
