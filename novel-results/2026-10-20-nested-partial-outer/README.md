# Inner returns can reactivate lanes excluded from the outer call

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**144 variants / 432 dispatches with exact controls, zero faults.**

Original depth-1 lanes excluded from an outer call can become active at a
nested inner return landing. Their r1 still contains the original lane ID,
because neither call issued in those lanes. This exact composition follows
`0 -> 2, 1 -> 0, deeper unchanged` for nonempty return; a call does not
implicitly preserve an outer conditional mask across these unreserved pops.

Exclude a prefix before a direct or uniform indirect outer call. Admit all
later lanes, which save the outer link and execute a three-target divergent
inner register call. The lowest admitted lane selects its target; only matching
admitted lanes enter. At the inner return landing, all nonparticipants run:
both admitted nonmatching lanes and the originally excluded prefix. Snapshots
read r0l=0 before pop and after pop 1. Originally excluded r1 remains its lane
ID, while admitted lanes hold the inner link. After two pops, every physical
lane is active. Zero/one-pop outer returns also follow the earlier
[early-return composition](../2026-10-20-nested-early-return/README.md).

Every saved r29 is explicitly initialized to the **valid outer continuation**
before divergence; admitted outer lanes save the same value through their
actual call. Thus reactivated excluded lanes never consume an uninitialized
transfer operand. Restoring r1 only affects issuing lanes. With zero/one inner
pops, matching inner participants retain their inner r1 at the final marker;
with two inner pops, all lanes receive the restored outer r1. All final
continuation markers are written by every physical lane after outer pop 2.

The matrix covers prefix lengths 1,5,16,24; both outer forms; three inner
winners; two seeded assignments; zero, one and two inner pops. A first case
for each pop count was inspected before extending the matrix. Every whole
actual program, all three winning paths and an independent no-call/no-return
conditional control pass complete scalar simulator gates first. Function and
inner-link addresses remain fixed; the changed outer displacement/link and
all transfer boundaries are verified after setup insertion.

All main/table words, inputs, inactive slots, pre-pop snapshots, link payloads,
fallback diagnostic and guards match independent oracles. Before/after
controls and all recovery checks are exact. Watchdog/kernel/memory diagnostics
are preserved, with zero faults or hangs. No model change is needed: simulator
4dd68e9 matches every original program.

This illustrates a calling-convention requirement: preserving an outer mask
needs explicit counter accounting around each nested call/reconvergence.
These probes intentionally omit that reserve; a balanced reserve/pops wrapper
is a separate follow-up. No claim is made that an uninitialized outer link
would be safe or that return automatically restores PTX participation.

```sh
python3 -B scripts/probe_nested_partial_outer.py --first 5 --pops 2 --hardware
make verify-nested-partial-outer
```

[Full evidence](../../results/2026-10-20-nested-partial-outer/README.md).
