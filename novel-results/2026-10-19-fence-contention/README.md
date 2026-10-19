# Fence cost with many SIMD groups per core: wall cost is group-count independent (no contention)

Status: confirmed on one device (driver-reported M2 Max G14C B1; user confirms board is a MacBook M2 Max),
direct DRM, compute stage, AC power, clock keeper holding the top clock. Straight-line programs
(`scripts/probe_fence_contention.py`, same shape as
[probe_fence_cost.py](../../scripts/probe_fence_cost.py): prologue + 32 x (context op, `wait 0`,
[fence]) + epilogue; the control omits the fence), Mesa-emitted barriers only, no loops.
Every program is exact-decode gated at construction and ends with `stop`. 210 dispatches,
all outputs correct, 0 faults or timeouts (hang budget untouched).

This closes the "multi-group fence contention" open item of
[remaining-work](../../docs/remaining-work.md) (safe-10).

## Test

Two grid configs of the same per-lane program: 32 lanes / `AGX_LOCAL_X` 32 (1 SIMD group) vs
256 lanes / `AGX_LOCAL_X` 256 (8 SIMD groups in one workgroup). A core-placement control
(`get_sr` SR20 stored per lane) confirms each config runs on exactly one core
([cores.json](../../results/2026-10-19-fence-contention/cores.json): 1 distinct core in both).
5 interleaved samples per cell; medians below (firmware ns, ~41.7 ns granularity).

## Results (firmware ns per dispatch; control = same program without the fence)

| Context | Config | Control | f533 | f59d | f59a | f533+f59a | f533+f59a+f59e | mesa_qf (7) |
|---|---|---|---|---|---|---|---|---|
| none | 1 group | 7,209 | 9,250 | 15,875 | 10,458 | 12,500 | 15,625 | 40,542 |
| none | 8 groups | 7,542 | 9,458 | 15,542 | 10,667 | 12,417 | 19,042 | 40,500 |
| store | 1 group | 11,875 | 12,417 | 19,083 | 15,000 | 15,541 | 26,875 | 53,917 |
| store | 8 groups | 11,709 | 12,583 | 19,125 | 14,917 | 15,792 | 27,666 | 55,833 |
| load | 1 group | 13,541 | 27,292 | 34,042 | 16,459 | 30,416 | 34,625 | 63,667 |
| load | 8 groups | 13,375 | 26,042 | 31,125 | 16,250 | 28,417 | 35,291 | 57,458 |

Per-cell sample spread is tight (max-min within ~8% in every cell; full table in the verifier),
so no clock-state transition confounds the comparison.

## Reading

- **Wall time is essentially group-count independent.** 17 of 18 fence cells match within
  12% (most within 5%); the one outlier (`none` context, f533+f59a+f59e: 15,625 vs 19,042 ns,
  +22%) still shows no serialization — 8x the groups cost 1.22x the wall time, not 8x.
  Fence stalls overlap across groups on a core instead of serialising. The amortised
  per-group fence cost drops ~6.5-8x, but the absolute wall cost of a fence sequence barely
  grows with group count. (The load-context mesa_qf cell goes the other way: the 8-group
  median is 10% *lower*, confirming the gaps are noise, not a systematic contention slope.)
- **The single-group context pattern reproduces** the [2026-10-18 fence-cost finding](../2026-10-18-fence-cost/README.md):
  f59a cheap in every context; f533 free after a store but expensive after a load; the
  invalidate-class barriers (f533, f59d, f59e, f599) add ~250-310 ns deltas after a load.
  Absolute per-fence ns here run ~2.4x above that table's (e.g. mesa_qf back-to-back
  ~1,042 ns/sequence here vs ~434 ns there) under the same keeper; the interleave makes the
  1-vs-8 ratio (the claim of this finding) immune to that level, but do not mix absolute
  numbers between the two runs. The `cost.rs` table keeps the 2026-10-18 values.
- For the cost model: charging each group's fences at the full single-group rate
  overestimates wall time of fence-heavy multi-group kernels by roughly the group count.
  The model change (charge device fences once per core, i.e. take the max rather than the
  sum across groups of a core) is recorded but **not applied**: this environment has no Rust
  toolchain (`agx_run` could not be rebuilt, so `verify-cost-model` cannot be re-run to
  accept it). The contention ratio here is the evidence that change needs.

Not established: more than 8 groups per core (needs >256-lane workgroups), fences racing
across workgroups/cores (only one workgroup ran here), interaction with L2-miss traffic.

## Reproduce

`scripts/probe_fence_contention.py hardware --n 32 --samples 5` (hardware, 210 dispatches;
starts and stops the clock keeper), `offline` to decode-gate only;
`make verify-fence-contention` (offline, checks every median above against
[results/2026-10-19-fence-contention](../../results/2026-10-19-fence-contention)).
No `agx_run` Rust-simulator gate was available in this environment (no Rust toolchain);
the code bytes are identical in shape to the gated `probe_fence_cost` programs (only the
grid dims differ) and every SB/fence program of this shape has run without fault.
