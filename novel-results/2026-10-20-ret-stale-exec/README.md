# RET conditionally changes counters and execution, preserving deeper stale bits

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**34 variants / 102 dispatches with exact controls, zero faults.**

For a nonempty issuing mask, RET updates lanes by their **counter value**:

| Incoming low r0 | Counter at target | Execution at target |
| --- | --- | --- |
| 0 | 2 | masked |
| 1 | 0 | active |
| 2..31 measured | unchanged | **unchanged**, including deliberately stale active bits |

Earlier [consistent counter/mask observations](../2026-10-20-deep-ret-counters/README.md)
could not distinguish this from assigning depth 2 to every issuing lane.
[Ordinary r0 writes](../2026-10-20-r0-write-mask/README.md) now let those states
be separated: initialize all physical lanes as active, write new low counters
without a mask synchronization, then execute RET to one uniform valid target.

With mixed 0,1,2,3 inputs, the first target checkpoint contains values 0,2,3
from original counter-1/2/3 lanes. Counter-0 lanes are masked. The next pop
synchronizes every live lane normally: only original ones execute after pop 1,
original 0/1/2 execute after pop 2, and all execute after pop 3. Thus deeper
stale active bits survive RET itself but not the subsequent pop. Uniform
nonzero cases still reach the target, including all-one (immediately active
zero) and all-31 (immediately active 31, then masked by the first pop). A zero
counter is therefore not required for RET to transfer when execution is active.

The matrix repeats the four ordinary-write forms with mixed/uniform depths
through 31 and both mixed rotations. The first unexpected mixed record keeps
its original all-false hypothesis classification; its complete readback is
independently explained by the conditional-update rule. Uniform 1/2/3 cases
were inspected before extending the matrix. All sources and indices are
initialized, every target is a decoded in-program instruction, and bounded
fallthrough/target drains terminate competing states without loops/barriers.

Every actual shader first passes the previous simulator's explicit issuing-
lane hypothesis. Independent no-RET/no-r0-write IF/jump controls construct
known depth 2 and check the same landing trace before/after each candidate.
Every main/table word, input, checkpoint, fallback marker and guard matches
independent hardware oracles. Watchdog/kernel/memory/recovery metadata is
preserved. No fault or hang occurred; all recovery controls pass.

Simulator 4dd68e9 assigns depth 2 by the cached execution mask and therefore
has **34 retained counterexamples**. Correcting this requires reading each
live counter for the 0/1 transitions and leaving deeper execution untouched.
The existing empty-issued RET fallthrough remains a separate measured guard.
All targets here are uniform r30 values; divergent target selection with stale
execution, other incoming states and timing remain separate questions.

```sh
python3 -B scripts/probe_ret_stale_exec.py --op mov-imm --maximum 3 --uniform --hardware
make verify-ret-stale-exec
```

[Full evidence](../../results/2026-10-20-ret-stale-exec/README.md).
