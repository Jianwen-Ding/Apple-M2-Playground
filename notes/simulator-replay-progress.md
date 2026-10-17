# Offline simulator replay progress

## 2026-10-17: memory replay gate

Added `make replay-memory-suite`, using the adjacent simulator's `suite_check`.
It checks all three categories separately: 50 device loads, 42 stores and 10
threadgroup layouts. Override `SIMREPO` and `MEMORY_SUITE` for another checkout
or a local retained-evidence subset. The target was run successfully over all
102 recordings, without GPU access. All 74 atomic-variant replays also pass.

Use a current simulator build: it now fails on mismatches, unsupported cases,
empty selections and shortened deterministic expected buffers. The new gate
does not change the retained evidence or approximate-transcendental tolerances.

No M2 hardware is available in the current Linux worker. New hardware claims,
float/u64 atomic timings and other calibration changes remain blocked on actual
measurements. Next: add bounded replay entry points for established cross-lane
and loop findings, keeping software-model results distinct from hardware data.

## 2026-10-17: complete retained control-flow replay

Added `make replay-control-suite` (`CONTROL_SUITE` overrides the default adjacent
simulator testsuite). All 23 recordings pass exact functional-output comparison,
including uniform branches, lane-dependent trips and nested control flow. This
supplements, rather than replaces, the 102 memory and 74 atomic replay checks.

The simulator's performance tracer now shares immutable lazy decoding across
groups, waves and overlap probes; registers, masks, taint and approximate memory
remain local. Raw 0x78 barriers now consume its execution budget. Existing
0x68/0x78 hardware findings and timing calibration are unchanged. Shared-cache
regressions compare fresh versus shared traces with distinct launch geometry,
uniforms and valid/skipped loads. No new hardware runs were performed.

Next: cross-lane replay entry points and data-dependent performance-trace
limitations. Hardware-only timing work remains blocked on an M2 device.

## 2026-10-17: established cross-lane families

Added `make replay-cross-lane-suite` using `suite_check --case-prefix`. All 130
retained full/masked SIMD and quad reductions, scans, shuffles and quad ballots
pass exact functional comparison. `CROSS_LANE_SUITE` selects a local suite;
missing families fail rather than silently passing an empty selection.

This supplements the 23 control, 102 memory and 74 atomic-variant replay checks.
The 16/64-bit width evidence remains a separate `verify-cross-lane-width` check;
these 130 standard testsuite recordings are not a new width/hardware result.
No retained evidence or timing calibration was changed. The simulator's new
memory-capture optimization is checked against the original address helpers
and all 36 complete prediction reports remain identical to their reference hash.

Next: resource/geometry replay coverage and bounded real-memory workload profiles.
New hardware timing remains blocked on access to an M2 device.

## 2026-10-17: complete standard integer-atomic replay

Added `make replay-integer-atomic-suite` (`INTEGER_ATOMIC_SUITE` overrides the
adjacent simulator testsuite). All 88 retained cases compare exactly: 44 device
and 44 threadgroup, all eleven integer operations, distinct/shared addresses,
returning/non-returning. This complements, rather than replaces, the 74 variant
replays and independent evidence verifier, both of which also pass.

The simulator caches immutable atomic fields and fixes an unnecessary next-source
register read in TG non-CAS operations. Synthetic register-boundary tests cover
all ten non-CAS operations and preserve CAS's comparison requirement. This is
not new hardware validation. Retained evidence, float/u64 variant behavior,
access suppression, group termination and timing calibration are unchanged.

All 358 selected simulator recordings compare exactly, 25 Rust tests pass, the
cost verifier has zero failures and all 36 complete prediction reports match
their retained hash. Focused CPU atomic improvements and the unresolved padded
standalone cost-trace slowdown are documented in the simulator's
`results/2026-10-17-atomic-execution/README.md`; no overall speedup is claimed.

Next: resource/geometry replay and real data-dependent profiles. New hardware
timing remains blocked on an M2 device.

## 2026-10-17: all standard geometry cases and bounded decode allocation

Added `make replay-geometry-suite` with `GEOMETRY_SUITE` override. All eight
retained 1-D/2-D/3-D cases compare exactly, including non-warp-sized workgroups;
five extend the prior replay selection, which now contains 363 exact cases.
This is standard functional output replay, not a new SR20 placement observation.
The existing `verify-sr-shape` evidence check remains separate.

Both simulator tracers now use a bounded dense decode prefix plus lazy tail
pages. Only immutable metadata is shared; instruction semantics, memory and
per-group state are unchanged. Synthetic regressions cover boundary-crossing
instructions, large jumps, decode errors and concurrent page creation. All 29
Rust tests pass, all 74 atomic variants replay, the cost verifier has zero
failures, and all 36 complete predictions match their retained hash.

Benchmark samples, including a rejected layout and long active-code controls,
are retained in the simulator's `results/2026-10-17-decode-pages/`. No hardware
evidence, timing calibration or expectations were changed. Next: launch guards,
resource replay and real data-dependent profiles. M2 hardware is unavailable.

## 2026-10-17: simulator launch-domain regression gate

Added `make verify-simulator-launch` / `scripts/check_simulator_launch.py`.
Synthetic stop-only programs check 34 invalid jobs, three malformed JSON lines,
and unchanged valid controls in one/four-worker batches. Malformed inputs must
fail without process aborts or lost/reordered result slots. Checks stay enabled
under Python -O, and failure injection correctly rejects the previous binary.
No GPU is used and no recorded hardware output is modified.

The simulator now validates launches before decoding, tracing, or materializing
functional buffers; fixes large-coordinate/occupancy overflow; and reports
batch errors without aborting later jobs. Empty performance grids now explicitly
report not modelled, rather than a nominal timing. Valid measured rules remain
unchanged. All 34 Rust tests, 363 exact recordings, 74 atomic replays and the
cost verifier pass; all 36 prediction reports match their retained hash.

`make verify-occupancy` also passes on all six retained evidence files, including
the 60-point 128-lane register sweep and shared-memory sweeps. No calibration or
hardware validation is added. Same-binary CPU A/A variability and measured launch
controls are retained in the simulator's `results/2026-10-17-launch-validation/`;
previous performance regressions are not declared resolved.

Next: lower-level geometry/resource replay and controlled workload profiling.
New hardware timing remains blocked on M2 access.
