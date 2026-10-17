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
