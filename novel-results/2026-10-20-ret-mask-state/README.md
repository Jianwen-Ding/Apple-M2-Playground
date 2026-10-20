# Return reactivates depth-1 lanes before reconvergence

Observed on M2 Max G14C B1, direct DRM, compute, AC power, 2026-10-20.
**57 variants / 171 dispatches including exact controls, zero faults.** This
corrects the assumption that return arrives with no active lanes and explains
the earlier stop/return discrepancy for shallow masks.

## Read before the first pop

Move each three-target return landing's 16-byte post-pop r1 snapshot to its
front, reading r0l instead. Preserve all instruction addresses, program size,
return target and post-pop markers. Across 36 scattered-mask cases (six first
positions, three winners, two seeds), **all and only the previously inactive
lanes execute before any pop, and they read r0l=0**. Originally issuing lanes
do not write this snapshot. Exact no-return jump controls read zero from the
originally active lanes, validating both the read and indexing.

The [earlier stop finding](../2026-10-20-empty-stop/README.md) compared return
with conditional-only masks using post-pop membership. That comparison missed
this earlier reactivation. A stop at the return landing has active depth-1
lanes to terminate; it is not an empty-mask stop on hardware. There is no need
to infer a special empty-stop rule from those shallow return records.

## Distinguish clearing from decrementing

Construct known incoming depths 0..M for M=0..4 using nested descending IFs.
Snapshot r0l/writer membership before pop and after each of four pops. Rotate
the lane patterns, compare ten actual returns with ten known-operation programs
that construct the proposed post-return state and jump to the trace. The
initial depth-3 exploratory return is also retained: 21 records in this family.

All traces fit this nonempty-return counter model:

| Incoming effective depth | Post-return behavior |
| --- | --- |
| 0 (issuing lane) | masked until two pops: represented as depth 2 |
| 1 | **already active at landing, r0l directly reads 0** |
| 2,3,4 | retain their corresponding pop/reactivation thresholds |

Thus the operational map **0 -> 2, 1 -> 0, deeper unchanged** matches every
complete buffer. It is not a general decrement: in the depth-3 trace only
original depth-1 lanes run after pop 1; original depth-2 lanes wait until pop 2.
Clear-all and subtract-two hypotheses also fail. Masked counters are not read
directly in this experiment; their retained depth is inferred from the verified
pop thresholds. A [later shuffle experiment](../2026-10-20-masked-r0/README.md)
also observes those low counter values directly, including masked source lanes. The active depth-1 reset is directly observed as r0l=0.

The original-state jump controls independently validate all initial depth
patterns. The known-operation state surrogates use only existing IF/pop/jump
forms, not an unvalidated ALU write to the execution counter. Their complete
hardware readbacks equal the corresponding return traces. A uniform full-group
return supplies two repeated baseline cases where the old and new models agree.

## Simulator and scope

Every exact program first passes the existing simulator's explicitly recorded
hypothesis. All uniform/jump paths and known-state constructions have full host
oracles. Hardware exposes **45 old-model counterexamples**: 36 pre-pop reads
and nine nonuniform-depth returns. Ten known-op state surrogates and two uniform
return baselines already match that model. The non-snapshot words, full main
output, input planes, guards, tails, recovery and kernel/memory diagnostics are
retained and checked independently.

The [combined return/stop correction](../../results/2026-10-20-ret-stop-model/README.md)
now models this rule and per-lane stop termination together. All 570 retained
programs replay exactly. The original 45 rejected hypotheses and source bytes
remain preserved, alongside independent hardware oracles.

Measured here: a **nonempty** issuing mask, full physical SIMD group, valid
uniform or three-way r30 targets, depths through four. [Empty-mask return](../2026-10-20-empty-ret-state/README.md) preserves state and
falls through. Deeper states, direct reads of masked counters and permanent partial-stop
termination remain follow-ups. Apply the transformation only to a nonempty issuing mask.

```sh
python3 -B scripts/probe_ret_prepop.py --first 1 --winner C --hardware
python3 -B scripts/probe_ret_levels.py --depth 4 --rotate 1 --hardware
python3 -B scripts/probe_ret_levels.py --depth 4 --rotate 1 --known-surrogate --hardware
make verify-ret-mask-state
```

[Pre-pop evidence](../../results/2026-10-20-ret-prepop/README.md) and
[depth evidence](../../results/2026-10-20-ret-levels/README.md).
