# Balanced per-call reserves preserve the enclosing execution mask

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**192 variants / 576 dispatches with exact controls, zero faults.**

The measured two-level calling convention is:

```text
push_exec r0l, 2       # immediately before each call, including nested calls
call ...              # save the incoming outer link before another call
... return ...
pop_exec r0l, 2       # reconverge this call before restoring/using its link
```

The push increments already masked counters by two and leaves issuing lanes
active. Each return's issuing lanes require two pops. Balancing each nested
call independently preserves the caller's original conditional mask. This
corrects the [unreserved nested behavior](../2026-10-20-nested-partial-outer/README.md),
where original excluded depth-1 lanes become active inside the nested flow.

The two reserves are tested independently, 0 or 2 at each level:

| Outer / inner reserve | Original excluded counter at inner return landing | Caller body after outer pop 2 |
| --- | --- | --- |
| 0 / 0 | 0, already reactivated | all physical lanes |
| 2 / 0 or 0 / 2 | 3, still masked there | all physical lanes, excluded lanes wake at outer RET |
| **2 / 2** | **5, still masked** | **only originally admitted lanes** |

These low counter values are read **directly** using initialized source lane
0 with an immediate shuffle, masking away unknown upper r0 bits. Original
excluded lanes remain living sources. The depth-5 observation extends the
previous direct depth-4 matrix. With both reserves, the inner pop 2 restores
excluded depth 3; outer return leaves it unchanged, and outer pop 2 restores
depth 1. An explicit original-IF pop then restores full participation.

All lanes entered in the final full-group marker. Admitted lanes retain the
restored outer r1; excluded lanes preserve their original r1 ID whenever a
reserve prevented them from participating in inner link restoration. With
no reserve, those lanes execute the restoration too and receive the outer
link. A final full-group marker alone therefore does not prove mask or link
preservation; intermediate caller and r1 planes independently distinguish it.

The matrix covers direct/indirect outer calls, prefix lengths 1/5/16/24, three
inner winners, two seeded assignments and all four reserve pairs. All saved
transfer operands are initialized to valid decoded in-program links. Every
whole actual/control/three-winner path passes scalar simulator gates before
hardware. Initial reserve-pair cases were inspected individually. The final
original-IF pop and further bounded drain pops precede termination, while all
reported diagnostics are stored before the drain. No loop/barrier is involved.

Every main/table word, input, masked destination, guard, link formula and
before/after no-call control is exact. Watchdog/kernel/memory/recovery evidence
is retained, with zero faults or hangs. Simulator 4dd68e9 already reproduces
every original program. No compiler implementation or timing claim is made.
The convention is measured at two call levels; deeper nesting, other incoming
counter states and other calling patterns remain separate follow-ups.

```sh
python3 -B scripts/probe_call_mask_reserve.py --outer-reserve 2 --inner-reserve 2 --hardware
make verify-call-mask-reserve
```

[Full evidence](../../results/2026-10-20-call-mask-reserve/README.md).
