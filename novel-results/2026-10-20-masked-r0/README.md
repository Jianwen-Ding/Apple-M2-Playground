# Directly reading masked execution counters

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**24 variants / 72 dispatches with exact controls, zero faults.**

The [return-depth trace](../2026-10-20-ret-mask-state/README.md) inferred masked
counter values from pop/reactivation thresholds. Immediate-index `simd_shuffle`
can also gather the initialized low r0 bits from masked source lanes. This
experiment directly observes the same return map: **0 -> 2, 1 -> 0, deeper
unchanged**, for depths through four.

Construct original depths 0..M with nested IFs, M=1..4, rotations 0 and 1.
Gather each of the 32 source lanes through both r0 and an independent payload
register r10. Repeat at a valid landing after one of three transfers:

- Original-state jump: both snapshots show original counters.
- Known-operation desired-state jump: reset the mask with four pops, construct
  the desired state using IFs and jump; the second snapshot shows that state.
- Return: the second snapshot exactly equals the desired-state program.

Writers in the first snapshot are original depth-0 lanes; return and desired
jump snapshots are written by original depth-1 lanes. Every writer sees the
same low counter value for every source lane, including masked source lanes.
The initialized r10 payload remains unchanged. For depth 4 the return gather
shows `0,1,2,3,4 -> 2,0,2,3,4`, while the payload gather still shows `0,1,2,3,4`.

The standard shader prologue initializes r0l on every physical lane before
masking. AND with 0xffff removes the unknown upper r0 half. Only immediate
shuffle indices 0..31 are used, avoiding quad-OR contamination from masked
index registers. Each address has a unique writer; no uninitialized source,
invalid target, out-of-bounds access, loop or barrier is involved. The 10.6 KiB
shader uses the direct harness's dynamic shader allocation.

Each candidate is surrounded by exact payload-only original-state jump
controls; these gather r10 in both banks and validate source selection, writer
masks and all addresses. Every complete original/desired/return program also
passes its independent simulator gate before hardware submission. The first
original, desired and return cases were inspected individually before the
matrix. All main/table words, untouched inputs, masked destinations, final
marker and guards match independent oracles. Watchdog, kernel/memory and
recovery diagnostics are retained. No new fault or recovery failure occurred.

This observation applies to initialized low r0 bits on full physical SIMD
groups. It does not characterize the high r0 half, terminated lanes, deeper
counters or PTX behavior for inactive source lanes. No model change is needed:
simulator d90cdcd already reproduces all programs exactly.

```sh
python3 -B scripts/probe_masked_r0.py --depth 4 --rotate 1 --mode ret --hardware
make verify-masked-r0
```

[Full evidence](../../results/2026-10-20-masked-r0/README.md).
