# Indirect call uses the lowest active target and writes links before filtering

Observed on M2 Max G14C B1, direct DRM, compute, AC power, 2026-10-20.
**74 variants / 222 dispatches including exact before/after controls, zero
faults, every recovery control passed.** Both target selection and the scope
of the implicit r1 write are now distinguished from earlier inferences.

## Winner and participation

For every k=0..31, activate the suffix k..31. Give lane k target B and all
other lanes target A, then swap addresses. Both callees are decoded in-program
blocks. Each records its entry marker and r1 **before** any reconvergence,
then pops once, records another marker and stops. No return, loop or barrier
is used. A separate fallthrough marker distinguishes transfer from skipping.
Repeat k=1 in both address assignments: 66 winner variants in total.

Every call chooses lane k's target, including when inactive physical lane 0
holds a different address. **Only the matching active lane k enters the callee
unmasked.** The other active lanes and inactive prefix remain masked until
the callee's pop. After that one pop, every lane stores the winning callee's
post-pop marker. Neither the other callee nor the fallthrough marker is stored.
Thus the group follows one selected program counter with other lanes masked;
these results do not implement independent calls to every lane's operand.

This agrees with the [return winner matrix](../2026-10-20-ret-winner/README.md)
on target selection but not participation: a divergent return does not mask
its active lanes according to operand agreement.

## The implicit link is written to all issue-active lanes

The entry-only r1 stores above cannot establish r1 in non-entering lanes.
Eight follow-ups change only the two callee snapshots from `iadd r28, r0l, 0`
to `iadd r28, r1, 0`, preserving code length, targets and surrounding code.
Initialize r1 in **all lanes** to `0xf1f10000` before the mask, then inspect it
after the callee pops and everyone is active.

For k=0,1,2,17,31 (both target assignments at k=1 and k=17, plus a repeat):

- **Every lane active at call issue receives the link**, including lanes whose
  different target prevents callee entry.
- Every initially inactive prefix lane keeps `0xf1f10000`.
- The link is exactly `shader_buffer_code_offset + call_pc + 2`.

In particular, with all 32 lanes active and lane 0 alone choosing B, all
32 r1 values become the link although only lane 0 writes the entry marker.
The current simulator writes links only in matching lanes, so its supported
lane-0-active prediction is wrong for this new trace. Earlier records that
stored links only at callee entry did not expose this difference. The new
post-pop snapshot corrects the old “links only in entering lanes” inference.
At k=31 the competing link-scope hypotheses coincide because just one lane is
active; this case is retained as a control.

## Validation and limits

All source values, target pointers, synthetic links, saved IDs and trace
addresses are initialized before masking. The exact program and both target
boundaries are decoded. Filtered uniform-call substitutions validate the
callee-entry partitions; forced direct-jump substitutions independently
validate both landing blocks with the expected synthetic link. For an empty
matching set, both empty-call fallthrough and a forced empty-mask landing are
simulated separately.

The actual lane-0-inactive simulator rejection is retained in 71 records.
Three lane-0-active variants simulate: the two entry-only cases match hardware,
while the post-pop link case is a new counterexample. The old link-scope
hypothesis remains recorded in the gate; hardware readback decides its failure.
The simulator has not yet been changed. Known-operation jump controls and
complete independent host oracles bracket every hardware variant.

These are full physical groups and contiguous suffix masks, two valid targets,
and one call with no return. Scattered masks, more addresses, nested divergent
calls and a qualified simulator update remain open. No arbitrary address,
security-sensitive stale-data form or unbounded execution is used.

A PTX backend must preserve the link for all issue-active callers and must not
assume a divergent AGX call runs every target. The selected subset alone enters
this callee; other targets need explicit compiler control flow.

```sh
python3 -B scripts/probe_call_winner.py --first 0                # known baseline
python3 -B scripts/probe_call_winner.py --first 1 --hardware
python3 -B scripts/probe_call_link_scope.py --first 1 --hardware
make verify-call-winner                                        # no GPU
```

Use `--repeat N` for another hardware record. The shared bounded watchdog
retains exact inputs/code, kernel deltas, firmware, memory and recovery state.
[Evidence and layout](../../results/2026-10-20-call-winner/README.md).
