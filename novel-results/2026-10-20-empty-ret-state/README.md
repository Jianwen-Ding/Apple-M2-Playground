# Empty-issued return preserves counters and falls through

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**16 variants / 48 dispatches with exact controls, zero faults.**

The [nonempty return matrix](../2026-10-20-ret-mask-state/README.md) established
an effective counter transformation `0 -> 2, 1 -> 0, deeper unchanged` through
depth 4. That transformation requires a nonempty issuing mask.

Construct only depths 1..M (M=1..4), with two rotations. Put five snapshots of
r0l and writer membership in both the bounded fallthrough and valid return
landing: before pop, then after each of four pops. A final fallthrough marker
distinguishes the locations. All eight actual empty returns follow the same
fallthrough as a wait instruction, leave depth-1 lanes masked until pop 1 and
preserve every deeper reactivation threshold. None executes at the target.

Eight known-operation surrogates construct the proposed `1 -> 0` state with IFs
and jump to the fallthrough trace. They show immediate depth-1 reactivation,
distinguishing the counter transformation from the observed empty-return
behavior. Original-state controls execute the same trace after replacing only
the two-byte RET with wait. All landing and fallthrough surrogate programs are
also checked exactly in the simulator before hardware submission.

The complete outputs, input words, trace planes, guards and tails match an
independent oracle. Every candidate has exact controls before and after it,
with kernel/memory/watchdog diagnostics retained. The recorded hardware boot
and shared fault budget remain unchanged; no recovery failed. These are
functional observations, with no latency inference.

The simulator's existing empty-issued return path already matches these cases;
keep its early fallthrough before applying the newly measured nonempty mask
transformation. Return targets are valid and uniform r30 values. This matrix
does not test invalid targets or counters beyond depth 4.

```sh
python3 -B scripts/probe_empty_ret_state.py --depth 4 --rotate 1 --hardware
make verify-empty-ret-state
```

[Full evidence](../../results/2026-10-20-empty-ret-state/README.md).
