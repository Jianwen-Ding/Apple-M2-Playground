# Barrier cost: 20-100 ns each back to back, but several cost 250-300 ns when they follow a load or store

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power, clock keeper
holding the top GPU clock. Unrolled straight-line chains (no loops), one 32-lane SIMD group, Mesa-emitted barrier
encodings only, every program gated in `agx_run` first. Firmware nanoseconds (24 MHz timer, ~41.7 ns granularity), so
read per-fence values to about +-15 ns.

## Method

A program is a prologue plus 32 units of `[context op, wait 0], [fence]`; the control has the same 32 units without the
fence. Per-fence cost = (median test - median control) / 32, from 15 interleaved samples of all 30 programs. An
independent 5-sample run agrees within 50 ns on every cell. Contexts: *back to back* (fences only, control is empty),
*store* (a coherent store before each fence) and *load* (a coherent load before each fence).

## Results (ns per fence)

| Barrier | back to back | after a coherent store | after a coherent load |
| --- | --- | --- | --- |
| f596 `memory_barrier` | 85 | 79 | 79 |
| f533 `unknown_barrier_1` (release) | 27 | **~0-13** | **247** |
| f59d `device_barrier_1` (acquire/invalidate) | 86 | 81 | **306** |
| f59a | 39 | 39 | 40 |
| f59e | 99 | **306** | 94 |
| f503 | 21 | 29 | **255** |
| f599 | 91 | 89 | **310** |
| f533 + f59d | 119 | 86 | 318 |
| Mesa's queue-family sequence (7 barriers) | **434** | **564** | **646** |

* The barriers fall into two groups when issued back to back: f533, f503, f59a cost 20-40 ns; f596, f59d, f59e, f599
  about 85-100 ns. The seven-barrier sequence costs about 430 ns, roughly the sum.
* **Context matters more than the barrier.** After a load, the barriers that invalidate (f533, f503, f59d, f599) add
  about 250-310 ns per fence: the next coherent load has to refetch. After a store, f533 is free but f59e costs 300 ns.
  This is a per-fence cost including its effect on the next memory operation, not the barrier's own latency.
* PTX-level estimate: a `__threadfence()` lowered to f533 costs 20-30 ns before stores and about 250 ns before a load
  that follows data loaded earlier; Mesa's seven-barrier sequence costs 0.4-0.65 us each time. Prefer f533 (+ f59d for
  acquire) over the whole sequence unless SB ordering is needed ([sb-lb finding](../2026-10-18-sb-lb/README.md)).

Not established: the cause of each context effect (cache line refetch is the likely mechanism for the load case),
costs with many SIMD groups per core, costs when the surrounding memory operations miss in L2, and whether the
effects add when fences are separated by ALU work. The simulator's cost model (`cost.rs`) now models the seven
barriers from this table (`FENCE_COSTS_NS`; per group, context = the last device store / load, penalty paid once; other `memory_barrier`
encodings cost 85 ns and are flagged unmeasured): single fences reproduce the table within 0.5 ns, the sequences within 17 ns (after a store,
Mesa's sequence is 71 ns high). `make verify-fence-model` checks it. Multi-group (core-level) fence contention is not modeled or measured.

## Reproduce

`scripts/probe_fence_cost.py hardware --samples 15` (starts and stops the clock keeper), `offline` to gate only;
`make verify-fence-cost` (offline, 14 checks against [results/2026-10-18-fence-cost](../../results/2026-10-18-fence-cost)).
