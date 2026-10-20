# Nested divergent register calls preserve explicitly saved outer links

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**12 variants / 36 dispatches with exact controls, zero faults.**

A direct or uniform indirect outer call can contain a three-way divergent
register call and complete an exact round trip when the outer link is saved
before the inner call and restored after two explicit pops. This validates
composition beyond the earlier uniform depth-two mixed-call examples.

All 32 physical lanes enter the outer function. Each stores and saves its
outer r1 link in r29. Initialized per-lane r30 operands name three valid
inner callees; lane 0 selects the winner. Only lanes whose target matches enter
that callee and write its identity and r1. Return targets the inner call's
buffer-relative link. At the inner continuation:

- All and only nonmatching lanes execute before pop and after pop 1, reading
  r0l=0 at both checkpoints.
- After pop 2, all lanes execute and read r0l=0.
- Every lane's r1 equals the inner link, including nonmatching lanes.
- Every lane's saved r29 still equals its outer link.

After restoring r1 from r29, outer return leaves the full group masked until
two pops. The main caller's pop-1 plane remains untouched; pop 2 writes the
final continuation marker and outer link in all lanes. A distinct fallback
marker remains untouched. Inputs, all masked destinations, output buffers,
guards and tails are exact. Direct outer links are call PC +6; indirect outer
and inner links are call PC +2, all relative to the shader-buffer base.

The matrix covers both outer forms, each winning callee A/B/C and two seeded
three-target assignments. Each program and all three possible winning paths
first match complete independent simulator oracles. A separate no-call,
no-return control uses only known moves, conditionals, pops and stores to
write the same trace; it passes before and after each candidate. Every byte
decodes and all targets/links are verified instruction boundaries in-program.
Initial direct and indirect cases were inspected before extending the matrix.
All watchdog/kernel/memory/recovery diagnostics are retained; no fault or hang.

Simulator 4dd68e9 already reproduces every program; no model change is needed.
The scope is full outer participation and explicit two-pop reconvergence
before restoring the saved link. Partial original outer masks, returning with
fewer inner pops, deeper divergent nesting and precise timing remain open.
Do not assume an uninitialized saved link is valid in a reactivated lane.

```sh
python3 -B scripts/probe_nested_divergent.py --outer indirect --winner C --hardware
make verify-nested-divergent
```

[Full evidence](../../results/2026-10-20-nested-divergent/README.md).
