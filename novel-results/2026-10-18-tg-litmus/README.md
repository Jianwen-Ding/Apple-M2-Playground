# Threadgroup memory behaves sequentially consistently between SIMD groups of one workgroup: no fence is needed

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power.
Straight-line litmus tests, no loops or spin-waits; Mesa-form `threadgroup_load` / `threadgroup_store` and
Mesa-emitted barriers only; 0 faults. Gated in the Rust simulator first.

## Test

16,384 lanes in 64-lane workgroups (two SIMD groups each). Each program starts by zeroing its slots and executing one
`threadgroup_barrier` (0x68) in every group, which aligns the two groups. Then lane `local` and its partner `local ^ 32`
(the other SIMD group) run, with F a variant between the two accesses:

* **SB:** `data[local] = 1; F; r = data[partner]`: violation = both lanes of a pair read 0.
* **LB:** `r = data[partner]; F; data[local] = 1`: violation = both read 1.
* **MP:** `data[local] = 1; F; flag[local] = 1`, then 8 times `flag[partner]; F; data[partner]`: violation = flag 1, data 0.

F = nothing, `wait 0`, `memory_barrier` (f596), f533, f59d, Mesa's seven-barrier sequence, a full 0x68 barrier or an
0x78 barrier (the last two as controls; every group executes them at the same point).

## Result

* **0 violations in all 72 runs** (3 kinds x 8 variants x 3 repeats), **including with no fence at all**.
* SB: every lane read its partner's store (1) even with F empty; LB: no lane ever read a later store; MP: the flag was
  seen on all 8 reads by every lane. Threadgroup memory is in program order at the observed timing: the other group's
  store is visible as soon as it is issued.
* For PTX: `fence.cta` / `membar.cta` between threadgroup-memory accesses of different warps in a block needs **no
  instruction** on this evidence; `bar.sync` only needs the 0x68 barrier for rendezvous
  ([0x68 vs 0x78 finding](../2026-10-11-barrier-0x68-vs-0x78/README.md)), not for visibility. Device-memory ordering
  across cores is different ([MP](../2026-10-11-memory-ordering/README.md), [SB/LB](../2026-10-18-sb-lb/README.md)).

Not established: the test is only as sensitive as its timing: the starting barrier keeps the groups close together, so a
reordering window much shorter or longer than the store-to-load distance used here could hide. Workgroups of more than two
SIMD groups, 0x78-scoped blocks, `threadgroup_atomic` (a separate [follow-up](../2026-10-17-tg-atomic-followup/README.md))
and imageblock memory were not part of this test.

## Reproduce

`scripts/run_drm_litmus_tg.py` (hardware), `make verify-tg-litmus` (offline, 6 checks against
[results/2026-10-18-tg-litmus](../../results/2026-10-18-tg-litmus)).
