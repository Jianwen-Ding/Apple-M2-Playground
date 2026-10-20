# Remaining G14C call/return work: agent handoff

Updated 2026-10-20. Use the latest measured rules below. The older A–G sections
retain useful construction/evidence history, with corrected mask and link rules;
old hypotheses in evidence records remain unchanged. The owner has authorized
higher-risk probing with close simulator gates, retained diagnostics and exact
recovery controls. Continue after a fault only if recovery is established;
persistent unresponsiveness stops further GPU submission.

Current evidence and integration:

- Lowest-active call/return target selection holds for suffix and scattered
  masks, two/three target addresses and both assignments. Register call writes
  r1 in every issue-active lane **before** operand selection and matching.
  `call r1` therefore falls through with the issuing mask unchanged.
  [Call/return model](../results/2026-10-20-control-simulator/README.md).
- Nonempty return maps low counters **0 -> 2, 1 -> 0, deeper unchanged** through
  depth 4. Original depth-1 lanes are already active at landing before any pop.
  Empty-issued return falls through with unchanged counters. Stop terminates
  issuing lanes and preserves masked survivors; an empty stop is a no-op.
  [Return/stop integration](../results/2026-10-20-ret-stop-model/README.md).
- Immediate shuffles directly read initialized low r0 of masked living sources.
  Stopped sources instead self-fallback and stopped index bits cease to
  contribute to the source quad's low-index OR. All five native simd shuffle
  forms have independent paired-index and poisoned-index hardware matrices.
  [Native shuffle integration](../results/2026-10-20-native-shuffle-model/README.md).
- Simulator **defc29d** replays all **2,403** original control programs exactly.
  Return/register call still require `AGX_EXPERIMENTAL_RET=buffer-pop2`;
  default rejection and target checks remain. Both interpreter paths have
  source-liveness fixtures; 44 library tests pass. Historical source and
  diagnostic hashes resolve through preserved source-before-model archives.

The [nested divergent matrix](../novel-results/2026-10-20-nested-divergent/README.md)
now validates direct/indirect outer calls with three-target divergent inner
calls, explicit two-pop reconvergence and saved-link restoration (12 programs,
36 dispatches, exact no-call controls, zero faults).

[Early-return composition](../novel-results/2026-10-20-nested-early-return/README.md)
now also validates zero/one inner pops: one pop reactivates matching inner
participants immediately at the outer landing; r1 restoration updates only
its issuing lanes. Twenty-four programs / 72 dispatches, exact controls, zero
faults. All saved outer links were initialized by a full original outer call.

[Partial original outer masks](../novel-results/2026-10-20-nested-partial-outer/README.md)
are now measured with initialized saved links: 144 programs / 432 dispatches,
exact controls and zero faults. Excluded depth-1 lanes reactivate at inner
return and preserve original r1 IDs until restoration.

[Balanced two-level reserves](../novel-results/2026-10-20-call-mask-reserve/README.md)
now preserve the outer mask: push_exec 2 before **each** call, paired with
return/pop2. Either missing reserve fails the caller-mask check. 192 programs /
576 dispatches, exact controls, direct masked counters 0/3/5, zero faults.

[Deep balanced nesting](../novel-results/2026-10-20-deep-call-reserve/README.md)
now validates 3/4/8 calls, mixed forms and a divergent leaf: 192 programs /
576 dispatches, exact controls, zero faults. Every frame restores its mask and
link; initialized masked source reads observe odd depths 3..17 directly.

[Consecutive counter reads](../novel-results/2026-10-20-deep-ret-counters/README.md)
now cover all 0..31: RET maps 0 -> 2, 1 -> 0, and preserves 2..31. Sixteen
programs / 48 dispatches, exact controls and both lane rotations, zero faults.

[Ordinary r0 writes](../novel-results/2026-10-20-r0-write-mask/README.md) preserve
the issuing mask until pop1 synchronizes from written counters (34 programs /
102 dispatches, four forms, exact controls and zero faults).

[Zero-count synchronization](../novel-results/2026-10-20-r0-pop0/README.md)
now selects only written zero-counter lanes after an ordinary write. All 34
programs / 102 dispatches have controls without pop0, exact buffers and zero
faults. Numeric masked post-pop0 counters are not directly read in that matrix.

[RET with stale execution](../novel-results/2026-10-20-ret-stale-exec/README.md)
now establishes conditional stored-depth updates: counter 0 -> masked 2,
counter 1 -> active 0, deeper counters/execution unchanged. Uniform nonzero
inputs still transfer. All 34 counterexamples now replay in c7e50f7; 102
dispatches, exact controls, zero faults.

[Unsigned counter boundaries](../novel-results/2026-10-20-wide-r0/README.md)
now cover sampled values through 0xffff, with both rotations: pop0 preserves
numeric values, RET preserves deeper counters, pop1 decrements unsigned, and
the final drain rejoins all living lanes. 36 programs / 108 dispatches, exact
independent payload controls, zero faults. Recorded AC-online is 0; no timing
claim. This does not test counter increment overflow or enumerate all values.

[Divergent targets with stale execution](../novel-results/2026-10-20-ret-stale-targets/README.md)
now select the lowest cached issuer before RET updates counter participation.
90 programs / 270 dispatches, three rotated destinations, suffix/scattered
and single-lane masks, independent no-RET controls and exact buffers, zero
faults. Sixty cases distinguish zero-counter selection, 66 updated execution,
36 both. No simulator change was needed; recorded AC-online is 0.

Next useful control questions: increment overflow, already-masked ordinary writes,
permanent termination through other mask operations, quad/other cross-lane
forms and precise timing. Earlier quiet out-of-program return observations
remain unmodelled; do not rerun invalid targets. New probes must retain actual
program gates, independent complete-buffer oracles and bounded watchdogs.

Current overflow follow-up: [one first-shuffle mismatch](../results/2026-10-20-push-overflow/README.md)
after 0xffff plus push1. Lane 12 stores 0x40 where source-0 counter zero was
predicted; every later word matches. Three programs / nine dispatches, exact
controls, zero faults/hangs, clean recovery. Do not treat this as an explained
overflow or timing rule yet; original evidence and source hashes are retained.
The [20 diagnostic follow-ups](../novel-results/2026-10-20-overflow-first-shuffle/README.md)
show first-shuffle destination retention across n1/n2/n3 and all five native
forms. A destination seed survives; wait0/pop0/a second shuffle fixes the
tested program, while one ordinary ALU instruction does not. Already-issuing
lanes behave normally. Combined 27 programs / 81 dispatches, exact controls,
zero faults, **18 simulator counterexamples** retained separately from the
2,403-program exact corpus. Next inspect masked destination writes and which
operation updates shuffle execution state before changing the functional model.

[Prepared-index destination probes](../novel-results/2026-10-20-overflow-register-visibility/README.md)
now separate the address calculation: immediate/copy/add also retain old
destination values in overflow-activated lanes, persisting through wait/drain.
Shuffle has lower/upper-half differences in the tested layouts. Four/five
intervening moves fail; six partially fixes immediate and fully fixes shuffle;
seven/eight fix the tested immediate. Counts are not calibrated cycles or a
universal pipeline rule. This adds 27 programs / 81 dispatches, exact controls,
zero faults, 17 counterexamples; combined overflow scope has 35 counterexamples
in 54 programs / 162 dispatches. The simulator limitation is still explicit.

The [overflow guard integration](../results/2026-10-20-overflow-guard/README.md)
now refuses unsynchronized masked-lane overflow activation by default. Wait0
or pop0 settlement is accepted; already-issuing wraps stay supported. This is
conservative and may reject empirically sufficient spacing. The explicit
`AGX_EXPERIMENTAL_EXEC_OVERFLOW=counter-sync` retains the incomplete old
hypothesis for diagnostics, not measured timing. Default raw replay accepts
11 exact and refuses 43 overflow programs; the opt-in retains all 35 known
counterexamples. All 2,403 earlier exact programs and 44 library tests pass.
The functional mask path also now skips stopped/absent lanes consistently.

Owner follow-up, deferred at their request: later inspect performance-simulator
pull requests from other branches for requested behavior/support, and implement
feasible requests with appropriate evidence and verification. Continue the
current probe investigation before that PR review.

## Established scope and files

Measured with one full 32-lane SIMD group on M2 Max G14C:

- Six-byte direct call: target = call PC + signed byte displacement;
  r1 = shader-buffer code offset + call PC + 6.
- Two-byte register call: uniform target = shader-buffer-relative byte address;
  r1 = shader-buffer code offset + call PC + 2.
- Return consumes a shader-buffer-relative byte address. Leave the code offset
  in the link. The default harness code offset is 0x2000.
- At the return destination, original issuing lanes need two pops, while
  original depth-1 lanes are already active and can execute stores or stop.
  Deeper live counters retain their values through the measured depth 4.
  A stop ends only lanes active there. This is not a general hardware stack.
- Two nested direct calls work when the outer link is saved in r29 and restored
  to r1 before the outer return. Timing is not calibrated.

The simulator's measured opt-in is `AGX_EXPERIMENTAL_RET=buffer-pop2`.
`AGX_EXPERIMENTAL_RET=1` enables a contradicted historical hypothesis and must
never gate a new hardware probe. The measured model supports the documented partial/divergent scope and empty
issue fallthrough. Hardware evidence, rather than acceptance by the simulator,
establishes those measured rules. New compositions still need independent
oracles and direct hardware checks.

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
marker on odd lanes only. Partial nonempty ret: the later direct reads correct the original inference —
ret maps `0 -> 2, 1 -> 0, deeper unchanged`, and transfers to the lowest active
operand. Empty-issued ret falls through unchanged. At landing, original
issuing lanes skip M1 (need 2 pops), while original depth-1 lanes already run
before pop 1. A single `pop_exec r0l, 2` reconverges
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

Measured 2026-10-17: the lowest active target wins (lane 0 in the original parity/swapped/alone
patterns, extended to every first-active lane and scattered masks). Only issue-active lanes addressed to the lowest-active target enter the
callee. Later post-pop reads establish that r1 is written in **every original
issue-active lane**, including nonmatching ones. Nonmatching lanes travel
masked and can resume after reconvergence. Both partitions reconverge (CONT2 everywhere).
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

2026-10-20 alias follow-up: [`call r1`](../novel-results/2026-10-20-call-r1/README.md)
fails to use its original target. Thirteen variants / 39 dispatches, no faults,
show fallthrough and the link in every issue-active r1; inactive r1 values stay
unchanged. Exact no-call controls verify the target copy. The current simulator
consumes the old operand and is wrong for this alias; `make verify-call-r1`
retains all counterexamples and nine refined known-op link/fallthrough gates.
Do not allocate an intended indirect target to r1. Model correction is next.

Alias correction, later 2026-10-20: nine pre-pop checkpoints show the original
issue-active mask persists immediately after `call r1`. The complete alias
corpus is now 22 variants / 66 dispatches, no faults. Simulator `d66f359` makes
the link write visible before operand selection/matching and replays all 408
original cases exactly. Current alias probes require actual-program equality;
old source/hypothesis versions remain archived. Empty/scattered aliases, more
callee addresses, nested divergence and the stop/return hidden state remain open.

Three-address extension, 2026-10-20: [72 variants / 216 dispatches](../novel-results/2026-10-20-three-targets/README.md)
with all three addresses live, scattered masks, six first-active positions and
rotated winners preserve the measured rules exactly. No new simulator change;
`make verify-three-targets` and the direct 480-case model replay pass. Next,
inspect r0/participation at a return landing before the first pop to distinguish
true empty-mask stop behavior from an unobserved return-mask transformation.

Return-arrival correction, 2026-10-20: [pre-pop reads and depth traces](../novel-results/2026-10-20-ret-mask-state/README.md)
show depth-1 lanes already active with r0l=0 at the landing. For nonempty issue
masks, `0 -> 2, 1 -> 0, deeper unchanged` fits all tested depths through four.
This explains shallow return/stop behavior without a special empty-stop rule.
57 variants / 171 dispatches, no faults; 45 current-model counterexamples remain
explicit (`make verify-ret-mask-state`). Probe empty issuing masks before
updating return, then correct active-lane stop termination/liveness together.
