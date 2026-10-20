# Register shuffle indices agree on stopped-source fallback

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**256 variants / 768 dispatches with exact controls, zero faults.**

Both immediate and register-index `simd_shuffle` return the issuing lane's own
source value when selecting a stopped lane. Selected living sources remain
readable even while masked. This extends the
[initial immediate-index observation](../2026-10-20-stopped-r0/README.md).

All 32 target indices are tested with incoming depths 0..M (M=1..4), rotations
0 and 1. Before divergence, every physical lane receives a unique lane-ID
payload and the same register index. Thus even subsequently stopped or masked
lanes have known low index bits, avoiding uninitialized quad-OR contamination.
Gather the chosen source with immediate and register forms before STOP, then
after one pop activates depth-1 survivors. Four more pops precede the final
survival marker. Candidate and control differ only by STOP versus wait.

All eight pattern/rotation sets agree, in both paired forms:

| Selected source at second gather | Observed value in each issuing lane |
| --- | --- |
| Originally active depth 0, now stopped | issuing lane's own ID |
| Original depth 1, now active | selected source's ID |
| Original depth 2..4, still masked | selected source's ID |

The first dead-source, active-source and masked-source cases were inspected
separately before the matrix. Every complete shader passes its recorded
simulator hypothesis before hardware; every hardware word fits an independent
scalar oracle. All controls, main output, initialized input, masked destination
slots, guards and final survival markers are exact. Watchdog/kernel/memory and
recovery diagnostics remain retained. No fault or hang occurred.

Simulator d90cdcd retains the source register after termination and therefore
misses **82** dead-source cases; the other 174 programs already match. The
initial [nine stopped-source cases](../2026-10-20-stopped-r0/README.md) are also
counterexamples. Uniformly seeded indices here do not yet distinguish whether
stopped lanes contribute to the quad's low-index OR. That is a separate
follow-up before generalizing source-liveness handling to divergent index
registers. Other native shuffle forms remain unmeasured for stopped sources.
This test does not read the stopped lane's underlying register storage.

```sh
python3 -B scripts/probe_stopped_shuffle_index.py --depth 1 --index 0 --hardware
make verify-stopped-shuffle-index
```

[Full evidence](../../results/2026-10-20-stopped-shuffle-index/README.md).
