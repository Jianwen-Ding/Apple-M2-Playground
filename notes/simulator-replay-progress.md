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
