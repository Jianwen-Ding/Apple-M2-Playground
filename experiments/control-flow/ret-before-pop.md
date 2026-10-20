# Direct observation at return landing before pop

Question before hardware, 2026-10-20: does return really arrive with no active
lanes, as the current simulator assumes? Previous membership traces were only
after pop. A stop at a return landing kills previously inactive lanes, unlike
an empty-mask stop constructed from conditionals. Perhaps those lanes are
already active before the first pop, making the stop ordinary termination.

Move each three-target return landing's 16-byte post-pop r1 snapshot to its
front and change the source to r0l. Keep every call/return PC, target address,
program length and output address fixed. The last table plane now records r0l
only for lanes active at the landing before any pop. Keep the post-pop marker
traces, input/guard/tail checks and independent no-return jump controls.

Gate every uniform/jump path and the exact actual shader against the current
empty-arrival hypothesis in the simulator; hardware decides it. The known jump
control reads zero from original active lanes before pop, checking the new
copy/addresses. Use source r30 and only valid in-program targets, no loops or
barriers. Start k=1, winner C, seed 103. Retain full watchdog/recovery diagnostics
and stop the batch for any changed non-snapshot word or fault. A failed recovery
or blocked host process stops GPU submission. `probe_ret_prepop.py [--hardware]`.

The first direct read shows all originally inactive lanes active at the return
landing with r0l=0. Extend the diagnostic with `probe_ret_levels.py`: construct
known original depths 0..M (M<=4) using nested descending comparisons, then
record r0l/writer membership before pop and after each of four pops. A known
no-return jump validates the original depths; another constructs the proposed
`active 0 -> 2, inactive d -> d-1` state and jumps to the same trace. This
separates decrement, clear-all and subtract-two hypotheses without writing r0l
through an unmeasured ALU trick. First actual case M=3, rotate 0; only proceed
past a saved outcome after exact recovery. All targets remain in-program.

The nonempty-depth matrix fits `0->2,1->0,deeper unchanged`. The next independent
question is an **empty** issuing mask. `probe_empty_ret_state.py` starts with
only depths 1..M, puts complete snapshots in fallthrough and at the valid return
landing, and records a final fallback marker. Exact wait controls and known
original/swap-state jump surrogates validate both paths. This distinguishes a
true no-op, a counter update with fallthrough, or a transfer after activation.
The first case is all depth 1; it must be inspected before extending the matrix.

The return/stop model now matches the saved operational traces. Next,
`probe_masked_r0.py` tests direct observation of **masked** low counters with
immediate-index simd_shuffle. The prologue initializes r0l in every lane;
AND with 0xffff removes the unknown upper half. Gather all 32 source lanes
through r0 and through independently initialized r10 before/after transfer.
Use three bounded variants: original-state jump, known desired-state jump,
and RET; a payload-only original-state jump is the exact recovery control.
All three complete programs must match simulator oracles first. Targets are
valid in-program instructions, each output address has a unique writer and
shader allocation grows dynamically in the measured C harness. Begin with
one original-state depth-3 case; inspect the complete readback and recovery
before proceeding to the return or a matrix. A mismatch is a finding requiring
analysis, not a reason to batch more hardware. Keep all watchdog diagnostics.

With masked-r0 access measured, `probe_stopped_r0.py` replaces one wait with
STOP in a nonempty partial mask, pops once to activate survivors, then gathers
all source low counters and initialized payloads. Final four pops and marker
check that stopped lanes remain absent. Only the wait/stop word differs between
candidate and control. Gate against retained-zero storage in the simulator,
classify hardware against low dead values 0/1/2/ffff without assuming any is
architecturally required. First depth-3 case only, inspect recovery before
extension. No source contains another dispatch's or uninitialized data.

Stopped-source gathers fit per-issuing-lane self fallback and cannot expose the
dead source's storage. `probe_stopped_shuffle_index.py` compares immediate and
register-index forms with the same target, seeding index r15 in every physical
lane before divergence/termination. Record both before STOP and after pop 1;
retain an exact wait control and final four-pop survival marker. Start M=1,
rotate 0, source 0 (dead); inspect, then separately source 1 (live active) and
M=3 source 2 (live masked). Only extend to other indices after exact recovery.
The complete actual shader is gated against the simulator's current retained
source hypothesis and hardware must fit a full independent self-fallback
oracle; preserve any discrepancy rather than widening the batch.

The all-index paired matrix agrees on stopped-source self fallback. Next,
`probe_dead_index_or.py` isolates low-index contributions: seed r15 in all
lanes, stop half at depth 0, pop once, then surviving lanes update r15 while
dead lanes retain the seed. Compare immediate/register reads with the same
new index. Exact wait controls update all living indices and must match first.
The actual shader is gated against the current simulator's retained-bit/source
hypothesis. Begin rotation 0, seed 3, target 0: retained dead bits select live
lane 3; ignored dead bits select stopped lane 0 and self-fallback. Both are
bounded, initialized, in-bounds cases. Inspect complete hardware classification
and recovery before extending seeds/targets or changing the simulator.

After simulator bf03118 corrects plain simd_shuffle liveness, test the four
other native forms separately with `probe_stopped_native_shuffle.py`: down,
up, xor and rotate_up. Keep source payload and index fully initialized and
compare immediate/register forms before STOP and after pop 1, with wait-only
controls and final survival marker. Exact current-model source hypotheses are
required before hardware. Begin each kind at depth 1, rotation 0, offset 1;
inspect its full fallback classification and exact recovery before extending
across depth 3, rotated masks and boundary offsets. No timing or cross-form
semantics are assumed from the plain shuffle finding.

The four native forms also self-fallback for stopped sources in the uniform
index matrix. Isolate low-index contributions independently with
`probe_native_dead_index_or.py`: seeded dead lanes versus survivor-updated
indices, paired immediate/register relative forms and exact wait controls.
The offline oracle preserves native up/down boundary behavior and quad-low
rotation/xor while distinguishing retained versus excluded dead seed bits.
Start each form at rotation 0, seed 1, new offset 2, inspect full recovery and
classification, then consider both rotations, all four low seeds and the ten
boundary offsets. Keep original hypotheses before any simulator correction.

Balanced deep calls directly observe odd masked counts through 17. Separately
isolate consecutive counters with `probe_deep_ret_counters.py`: construct
incoming depths 0..M, M=5/7/15/31, gather all 32 low-r0 sources before/after
an original-state jump or uniform nonempty RET. Payload-only original-state
controls validate indices, addresses, writer masks and all buffers. The only
change to the measured gather layout is a longer bounded final drain after
snapshots; target/gather PCs stay fixed. All whole paths must pass the current
explicit deeper-counter hypothesis and scalar oracle first. Start M5 original
and inspect, then M5 RET separately; inspect before increasing to M31. The
M31 case places all consecutive 0..31 values in one initialized physical group.
A rotation swaps which physical lanes issue/observe RET. No uninitialized high
half is retained; AND masks it away. Keep watchdog/recovery diagnostics.
