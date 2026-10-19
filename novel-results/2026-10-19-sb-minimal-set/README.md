# Minimal sufficient SB fence set: f533 + f59a (+ f596 for coherent stores)

Status: confirmed on one device (driver-reported M2 Max G14C B1; user confirms board is a MacBook M2 Max),
direct DRM, compute stage, AC power. Straight-line store-buffering litmus, no loops or spin-waits,
Mesa-emitted encodings only (coherent loads; normal u4 = 4 or coherent u4 = 7 stores).
65,536 lanes in 32-lane workgroups; lane i and lane i ^ 32 form a pair on different workgroups.
Each lane owns one table word (zero at start). SB shape: `v[i] = 1; [fence]; r[i] = v[partner]`;
violation = both lanes of a pair read 0. `wait 0` between store and fence in all runs here.
Gated by exact decode (`DA.decode_lengths` at construction) and a `stop`-terminated whole program;
0 GPU faults or timeouts in 260 + 3 dispatches (hang budget untouched).

This closes the "minimal sufficient SB fence set" open item of
[remaining-work](../../docs/remaining-work.md) (safe-10) and extends the
[SB/LB finding](../2026-10-18-sb-lb/README.md).

## Results (32,768 pairs per run, 10 repeats per cell, `wait_between` = 1)

| Fence (in order) | Normal stores | Coherent stores |
|---|---|---|
| f533 | 464-752 every run | 208-1,936 every run |
| f533+f503 | 160-624 every run | 272-1,600 every run |
| f533+f596 | 0-96 (6/10 nonzero) | 0-288 (9/10 nonzero) |
| f533+f599 | 0-208 (5/10 nonzero) | 0-80 (8/10 nonzero) |
| f533+f59d | 0-192 (6/10 nonzero) | 0-112 (9/10 nonzero) |
| **f533+f59a** | **0 in 10/10** | 0-32 (2/10 nonzero: 16, 32) |
| f533+f59e | 0-48 (4/10 nonzero) | **0 in 10/10** |
| f596+f533+f59a | **0 in 10/10** | 0-16 (2/10 nonzero) |
| **f533+f59a+f59d** | **0 in 10/10** | **0 in 10/10** |
| **f533+f59a+f59e** | **0 in 10/10** | **0 in 10/10** |
| **f533+f59a+f599** | **0 in 10/10** | **0 in 10/10** |
| **f533+f59a+f596** | **0 in 10/10** | **0 in 10/10** |
| Mesa queue-family sequence | 0 in 10/10 | 0 in 10/10 |

Combined with prior evidence (same harness, same shape):
- f533+f59a, normal stores: **0 violations in 33 runs** (sb2 3 + sb3 20 + this 10) =
  1,081,344 pairs. Every other 2-barrier form leaks; no single barrier works.
- f533+f59a, coherent stores: 4 runs of 30 leak 16-64 pairs each (sb3 2/20 + this 2/10).
  Rare but real (~5e-4 of pairs in a leaking run, 0 otherwise).
- f596+f533+f59a, coherent: 4 runs of 30 leak 16 pairs each. A barrier *before* f533/f59a
  does not fix the coherent leak (order matters: f59a+f533 and f59d+f533 also leak badly).
- Any tested third barrier *after* f59a (f59d, f59e, f599, f596): 0 in 40 runs (10 each,
  both store policies) plus sb2's f533+f59d+f59a 0 in 6 runs.

## What this decides for PTX

- `fence.sc.gpu` / `__threadfence()` in SB position (store, fence, then a load of another
  core's data): emit **f533, f59a, f596 in that order** (all three known-good thirds work;
  f596 is picked because it is cheap after a store, ~79 ns in the
  [fence-cost finding](../2026-10-18-fence-cost/README.md), versus f59e at ~306 ns).
  Estimated cost from that table (after-store context): f533 ~0 + f59a 39 + f596 79 ≈ 120 ns.
- If the store policy is known normal (non-coherent), **f533+f59a alone suffices**
  (0 in 33 runs, ≈ 40-65 ns estimated).
- Coherent stores need the third barrier. Order is load-bearing: additions must come
  *after* f59a; f596 *before* f533 does not help.
- Statistical limit: a leak rarer than ~1e-5 per pair cannot be excluded by 10 clean runs.
  The coherent-store leak of f533+f59a was caught only because it leaks ~2/10 runs.

Not established: whether f533+f59a+f596 also covers the LB shape (LB never leaks with any
fence, so nothing to cover), threadgroup-memory SB (no fence needed there:
[tg-litmus](../2026-10-18-tg-litmus/README.md)), 16-lane or 64-lane workgroup shapes.

## Reproduce

`scripts/run_drm_litmus_sb_lb.py --lanes 65536 --repeats 10 --kinds sb
--fences f533+f59a,f533+f599,f533+f59e,f533+f59d,f533+f596,f533+f503,f596+f533+f59a,f533+f59a+f59d,f533+f59a+f59e,f533+f59a+f599,f533+f59a+f596,mesa_qf,f533
--store-coherent 0,1 --waits 1` (hardware, 260 dispatches),
`make verify-sb-minimal` (offline, checks every number above against
[results/2026-10-19-sb-minimal](../../results/2026-10-19-sb-minimal)).
