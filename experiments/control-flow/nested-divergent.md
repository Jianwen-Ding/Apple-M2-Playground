# Nested divergent call composition

2026-10-20, before hardware: validate two-level direct/indirect outer calls
with a three-target divergent inner register call. All 32 physical lanes enter
the outer function and save their outer link before the inner call. Save ID
before r1 clobber. Inputs select only decoded in-program A/B/C instructions.

Snapshot inner entry/link, r0l at inner continuation before pop and after each
of two pops, then r1 and saved outer link on the reconverged full group. Only
after two pops restore outer r1 and return. Main caller snapshots after pop 1
(must remain unwritten), then after pop 2 and finishes. Bounded fallbacks write
a distinct BAD marker; no loop, barrier, uninitialized source or invalid target.

Every whole actual shader and all three target-winning paths must match a
scalar complete-buffer oracle before hardware. A separate no-call/no-return
conditional control writes the same full trace using known operations, and
must match exactly before/after each candidate. Enumerate all instruction
boundaries and require every call/return target and link to be one. Use the
shared watchdog/recovery harness, retaining diagnostics even on a fault/hang.
First direct outer, winner A, seed 17 only; inspect every word and recovery
before varying outer form, winner or random seed. Partial original outer masks
and fewer inner pops remain separate follow-ups because they can reactivate
lanes whose saved link was never initialized by a call.

The two-pop nested matrix is exact. Next `probe_nested_early_return.py` removes
one or both inner pops without moving any function or link address, then
returns from the outer function using the lanes that are already active.
All saved outer r29 values were initialized by the full-group outer call;
inactive r1 values are never consumed as a transfer target. Add a main landing
snapshot before any pop, consuming only STOP padding and keeping targets fixed.
The scalar hypothesis predicts that one inner pop leaves matching lanes at
depth 1; the next RET reactivates them immediately at the outer landing.
Restoring r1 before they reconverge only changes nonmatching lanes, so the
final r1 payload must retain inner links in matching lanes. Exact no-call
controls construct that full trace. Start direct/A/seed17/one pop; inspect every
word and recovery before the zero-pop case or broader target/form variation.

Full-group early returns also match. `probe_nested_partial_outer.py` now
excludes an original prefix from the outer call, preinitializing every saved
r29 to the newly computed **valid outer continuation** before divergence.
Original excluded r1 remains its initialized ID and is observed before link
restoration. Only originally admitted lanes execute outer entry/save and inner
call; a nonempty inner return may reactivate excluded depth-1 lanes anyway.
All restored transfer operands are therefore initialized in-program values.
Insertion consumes STOP padding and repatches only the direct outer displacement
and its expected link; function addresses and inner link stay fixed. Complete
actual/control/three-winner paths must match scalar oracles. First direct,
k1/A/seed17/two pops, inspect full recovery, then one/zero pop cases separately
before extending first positions, outer form, winner and seed. Stop further
submissions for any failed recovery or blocked process; preserve diagnostics.

Unreserved partial-outer cases are exact. Test a compiler-oriented balanced
wrapper with `probe_call_mask_reserve.py`: immediately before each call,
`push_exec r0l, 2` increments only masked counters; normal RET/pop2 balances
that call's reserve. Vary outer and inner reserve independently (0/2 each).
Keep saved transfer operands initialized, all functions/links decoded in-program,
and add a final original-IF pop plus full-group markers before termination.
Eight further bounded pops after diagnostics drain alternative depth hypotheses
without changing earlier observations. Read initialized masked lane 0's low
r0 via immediate shuffle at inner return arrival: predicted 0/3/5 for total
reserve 0/2/4. Separate known-op controls write exact scalar traces; gate every
actual/three-winner/control path. First both reserves 2, direct/k1/A/seed17;
inspect all words and recovery before outer-only, inner-only, neither, or a
matrix. The convention is a hypothesis until those hardware contrasts agree.
