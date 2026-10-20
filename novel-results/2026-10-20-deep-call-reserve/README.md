# Balanced reserves preserve caller masks through eight calls

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**192 variants / 576 dispatches with exact controls, zero faults.**

The [balanced two-level convention](../2026-10-20-call-mask-reserve/README.md)
continues to work through 3, 4 and 8 calls: reserve two counts immediately
before **every** call and pop two after its return. Each function saves its
incoming link in a distinct register before calling its child, then restores
it only after the child reconverges. The last call selects among three
initialized valid leaf targets. Static callers use direct, indirect or mixed
forms. The original suffix mask is preserved at every measured continuation.

Immediate shuffles read the initialized low r0 of excluded source lane 0:

| Call depth reached | Excluded counter at function entry | Counter after its matching caller's pop 2 |
| --- | --- | --- |
| 1 | 3 | 1 |
| 2 | 5 | 3 |
| 3 | 7 | 5 |
| 4 | 9 | 7 |
| 5..8 | 11,13,15,17 | 9,11,13,15 |

At the divergent leaf, matching admitted lanes enter and store the leaf link,
identity and deep counter. After leaf return, only admitted nonmatching lanes
run before pop and after pop 1; they read that same deep excluded counter.
After pop 2 all admitted lanes rejoin and read the restored enclosing count.
Upper returns mask all admitted lanes until pop 2, while originally excluded
lanes remain masked. Each reconverged r1 exactly equals its corresponding
call's buffer-relative link, with +6 for direct and +2 for indirect forms.

After the top call returns, the caller marker is written only by originally
admitted lanes. Popping the original conditional then writes a full-group
marker and final r1: admitted lanes have the outer link; excluded lanes retain
their original IDs. Every entry, pre-pop, pop-1 and post-pop checkpoint is
checked per frame, including slots that must remain untouched. Unknown upper
r0 bits are masked away; every source/index is initialized within this shader.
These are odd counter values through 17, not an exhaustive test of every
integer depth in that range.

The matrix covers four original suffix starts, three leaf winners, two seeds
and eight depth/pattern combinations: all four static call combinations at
three calls, both alternating patterns at four/eight calls. Initial 3-, 4- and
8-call programs were inspected individually before the matrix. All saved-link
registers are initialized to a valid main continuation before divergence,
then overwritten by each admitted function entry. This prevents consuming
uninitialized targets under a competing reactivation hypothesis. Functions and
links are all decoded in-program boundaries. Final bounded drain pops follow
all reported diagnostics; no loop/barrier is involved.

Every actual program and all three winning paths first match full scalar
simulator oracles. Independent no-call/no-return conditional controls produce
the same trace and pass before/after every candidate. Full main/table words,
inputs, original-mask preservation, links and guards are exact. All watchdog,
kernel/memory and recovery evidence is retained; zero faults or hangs.
Simulator 4dd68e9 already reproduces all programs; no model change or compiler
implementation is included. Deeper nesting, consecutive high counter values,
other incoming states and timing remain separate questions.

```sh
python3 -B scripts/probe_deep_call_reserve.py --depth 8 --pattern alternating --hardware
make verify-deep-call-reserve
```

[Full evidence](../../results/2026-10-20-deep-call-reserve/README.md).
