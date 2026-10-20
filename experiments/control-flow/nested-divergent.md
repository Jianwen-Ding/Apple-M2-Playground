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
