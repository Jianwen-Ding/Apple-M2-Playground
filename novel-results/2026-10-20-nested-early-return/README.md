# Returning before inner reconvergence exposes counter and link composition

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**24 variants / 72 dispatches with exact controls, zero faults.**

The [nested divergent baseline](../2026-10-20-nested-divergent/README.md)
reconverges with two pops before restoring the outer link. With zero or one
inner pop, an outer return can still reach its valid continuation using only
the already active nonmatching lanes. Matching inner participants remain
masked during that r1 restore, so their final r1 retains the **inner** link.

All physical lanes entered the outer call and initialized saved r29 with a
valid outer link before the divergent inner call. At the inner return landing,
nonmatching lanes are active; matching participants are at depth 2. Removing
one/both pops uses same-size wait replacements, keeping all function/link
addresses fixed. Before outer RET, only nonmatching lanes restore r1 from r29.
No masked participant's inner r1 is used as the outer transfer target.

| Inner pops before outer return | Matching participants at outer landing |
| --- | --- |
| 0 | Remain masked at depth 2; no pre-pop or pop-1 writes |
| 1 | Their depth 1 becomes **active immediately**, r0l=0 before any outer pop and after pop 1 |

In both cases outer-return issuers are masked until pop 2. After pop 2 every
lane writes the final continuation marker. Nonmatching lanes have the restored
outer r1; matching lanes retain their inner r1. Every saved r29 remains valid,
though only current issuers can write its pre-return snapshot. This exact
composition agrees with `0 -> 2, 1 -> 0, deeper unchanged` for each nonempty
return, without an additional hidden nested-return rule.

The matrix covers direct/indirect outer calls, each of three inner winners,
two seeded assignments and zero/one inner pop. A newly inserted outer-landing
pre-pop checkpoint consumes STOP padding without moving functions or links.
Every target/link remains a decoded in-program boundary. Every whole actual
program, all three winning paths and an independent no-call/no-return
conditional control pass simulator and scalar complete-buffer checks first.
Initial one-pop and zero-pop cases were inspected before extending the matrix.
All control/main/table words, inputs, masked destinations, fallback plane and
guards are exact; every recovery passes. Watchdog/kernel/memory evidence is
retained. No fault or hang occurred; no timing inference is made.

Simulator 4dd68e9 already matches every original program. This is a functional
observation of full original outer participation. Partial outer masks need
separate work because newly active lanes may never have saved an outer link.
The result also shows why r1 restoration must follow intended participation;
a final full-group marker alone does not prove all lanes restored their links.

```sh
python3 -B scripts/probe_nested_early_return.py --pops 1 --hardware
make verify-nested-early-return
```

[Full evidence](../../results/2026-10-20-nested-early-return/README.md).
