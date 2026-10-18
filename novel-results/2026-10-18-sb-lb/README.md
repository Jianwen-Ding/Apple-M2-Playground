# Store buffering (SB) and load buffering (LB) across cores: SB needs f533, LB was never observed

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power.
Straight-line litmus, no loops or spin-waits, Mesa-emitted encodings only (coherent loads; stores with Mesa
u4 = 4 or 7). 65,536 lanes in 32-lane workgroups; lane i and lane i ^ 32 form a pair on different workgroups.
Each lane owns one table word; the table starts at 0. The SR20 core of each lane is recorded.

* **SB:** `v[i] = 1; [fence]; r[i] = v[partner]`. Both lanes reading 0 is impossible under sequential consistency
  at any relative timing (each load would precede the other lane's store), so it counts as a violation.
* **LB:** `r[i] = v[partner]; [fence]; v[i] = 1`. Both lanes reading 1 is the violation.

## Results (32,768 pairs per run)

| SB fence between the store and the load | Violating pairs per run |
| --- | --- |
| none, `memory_barrier` (f596) alone, or `device_barrier_1` (f59d) alone, or f59a alone | 31,000-32,600 (about half) |
| **f533 alone** | 304-1,264 (under 4%) |
| f596 + f533 | 208-928 |
| f533 + f503; f59d then f533; f59a then f533 | still nonzero (up to about 1,100 pairs) |
| f533 + f59a, normal stores | **0** in 23 runs |
| f533 + f59a, coherent stores | 0-48 (10 repeats show up to 48) |
| f533 + f59d (3 runs) | 0-96 |
| **Mesa's queue-family sequence** (f596 f533 f59a f59e f503 f599 f59d) | **0** in 28 runs, both store policies |
| that sequence minus any one of f596, f59a, f59e, f503, f599, f59d | 0 in 8 runs each |
| that sequence minus f533 | normal stores: up to 31,792 violating pairs; **coherent stores: 0** |

* Violating SB pairs never involved two lanes on the same core. Messages crossing cores need both a release (f533) for
  normal stores and the later barriers to make the store visible to the partner's load.
* **LB: 71 of 72 runs had no violating pair** (3 repeats of every fence and store policy). The one exception was
  32 pairs in a single `f533` run with coherent stores and no wait, which did not repeat. Loads are not observed moving after later stores, but the sample is small and mostly loads
  that ran before the partner stored.
* With `wait 0` between the store and fence the numbers do not differ meaningfully from the no-wait variant.

## What this decides for PTX

* `fence.sc.gpu` / `__threadfence()` followed by a load of another core's data (SB shape) needs more than f533:
  emit **f533 followed by the rest of Mesa's queue-family sequence**, or at least f596 + f533 + f59a...f59d, until a
  minimal sufficient set is found. Every shorter sequence tried leaked.
* f533 alone gives release semantics for MP ([memory-ordering finding](../2026-10-11-memory-ordering/README.md)) but
  not SB.
* Coherent stores remove the dependence on f533 when the full tail is present.
* No evidence that LB needs an extra fence.

Not established: a minimal sufficient fence set for SB; whether the rare coherent-store leaks (f533 + f59a) are real
or an artifact of timing; threadgroup-memory SB/LB (open in safe-10); behavior across dispatches.

## Reproduce

`make test-sb-lb` (hardware, one repeat of the full matrix; `scripts/run_drm_litmus_sb_lb.py --fences A+B ...` for
combinations), `make verify-sb-lb` (offline, checks every number above against
[results/2026-10-18-sb-lb](../../results/2026-10-18-sb-lb)). The programs were gated in the Rust simulator (`agx_run`)
before the first submission.
