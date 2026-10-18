# A device atomic is not a release: the flag atomic needs the same f533 as a store

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power.
Straight-line message-passing litmus, no loops or spin-waits, Mesa-named atomic ops only (add = 0, xchg = 2) and
Mesa-emitted barriers. Same shape as the [MP finding](../2026-10-11-memory-ordering/README.md): each of 65,536 lanes stores
`data = 1`, a writer fence, then sets `flag` (store, atomic add, atomic add with return, atomic exchange); it then reads a
lane of the neighbouring workgroup 16 times: flag, `wait 0`, [reader fence], data. Violation = flag 1 with data 0.

## Results (1,048,576 reads per run, 3 runs per cell)

| Writer fence | Flag by store | Flag by atomic add / add+ret / xchg |
| --- | --- | --- |
| none | 72,000-109,000 violating reads | **570,000-810,000** |
| `memory_barrier` (f596) | 32,000-72,000 | **580,000-766,000** |
| **f533**, reader f59d | **0** | **0** (all three atomics) |
| f533, no reader fence | 0-240 | 256-2,400 |
| Mesa's queue-family sequence, reader f59d | 0 | 0 |

* **An atomic flag is no release.** Without f533 the atomic flags are visible almost immediately (flag seen in 85-99% of
  reads, versus 17-50% for a store) but the data is mostly stale: the atomic goes straight to the coherence point
  while the earlier data store is still in a core-local queue. This makes message passing worse than with a store.
* With f533 before the atomic and f59d between the flag and data loads, MP never failed: 0 in 3 runs of each atomic form
  (add, add with return, exchange) and of the store.
* Returning the old value (`wait 0` after the atomic) does not order the earlier store.
* Same-core pairs never violated.

## PTX mapping

* `atom.release.gpu` / `red.release.gpu` (and `atom.acq_rel`): emit **f533 before the atomic**, as for `st.release`.
* `atom.acquire.gpu`: the atomic, `wait 0`, then **f59d** before later loads.
* Do not rely on `atom.relaxed` to publish earlier stores, even though the atomic itself is globally visible quickly.

Not established: atomics as the acquire side, atomics on threadgroup memory, 64-bit atomics (none known), exchange as
a lock hand-off.

## Reproduce

`scripts/run_drm_litmus_atomic.py` (hardware; gated in the Rust simulator first), `make verify-atomic-release` (offline,
27 checks against [results/2026-10-18-atomic-release](../../results/2026-10-18-atomic-release)).
