# Return preserves every consecutive masked counter from 2 through 31

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**16 variants / 48 dispatches with exact controls, zero faults.**

Direct initialized masked-source r0 reads confirm the nonempty return map
**0 -> 2, 1 -> 0, all other measured counters 2..31 unchanged**. This extends
the [depth-4 direct reads](../2026-10-20-masked-r0/README.md) and complements
[deep balanced calls](../2026-10-20-deep-call-reserve/README.md), which tested
odd counter values through 17 in a nested calling convention.

Construct depths 0..M using descending IFs, M=5,7,15,31. Gather all 32 source
lanes' low r0 bits and initialized depth payload before and after an original-
state jump or uniform valid RET. At M31 each consecutive 0..31 value occurs
exactly once. Two lane rotations move the issue/observation roles; rotation 1
puts the only issuing depth-0 lane at lane 31. Before return only original
depth-0 lanes write, and after return only original depth-1 lanes write. Every
writer observes the complete same source-counter vector.

The original diagnostic layout and valid return target remain fixed. The only
layout extension is a longer bounded drain **after** both gather snapshots,
ensuring every physical lane reaches final marker/termination for larger
initial depths. Source upper bits are masked away with 0xffff; immediate
indices avoid index-register contamination. A payload-only original-state jump
is the exact control before and after each candidate. All actual/control/
original paths pass full scalar simulator gates first. Maxima were increased
stepwise and the original/return outcomes checked before rotating the matrix.

Every main/table word, input plane, inactive destination, marker and guard is
exact against an independent oracle. All recovery controls pass, with complete
watchdog/kernel/memory diagnostics preserved. No fault or hang occurred.
Simulator 4dd68e9 already matches these programs. No counter-width limit,
values above 31, empty-issued return transform or timing claim follows.

```sh
python3 -B scripts/probe_deep_ret_counters.py --maximum 31 --rotate 1 --mode ret --hardware
make verify-deep-ret-counters
```

[Full evidence](../../results/2026-10-20-deep-ret-counters/README.md).
