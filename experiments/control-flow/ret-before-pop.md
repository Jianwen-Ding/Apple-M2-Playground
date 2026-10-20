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
