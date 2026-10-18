# PTX-compliant sin: the fma-split argument reduction costs nothing measurable

Status: one device (M2 Max G14C), direct DRM, straight-line, simulator-gated before the GPU (45 / 50 instructions per lane for a short chain
agreed with the model: all results in [-1, 1]). 0 faults, no hang-budget use. Answers safe-02 item 5.

## Test

Each lane runs a dependent chain of K sine evaluations on its own value (the result feeds the next input), K = 1, 64, 128, 131,072 lanes, 5 runs per
point, firmware time. The cost per evaluation is the slope against K.

* **mesa:** `turns = x * c; fract = turns - floor(turns); q = fract * 4; y = sin_pt_1(q); r = sin_pt_2(y) * y` (7 instructions).
* **fma:** `turns = fma(x, c_hi, x * c_lo)` in place of `x * c` (8 instructions; the sequence that keeps PTX `sin.approx` within its error bound,
  see the simulator's `record_sincos_chain.py`).

## Result

* Mesa: **1.06 us per evaluation** per 131,072 lanes; fma-split: **1.05 us**. The difference is under 2% (the extra `fmul` and the `fmul` -> `fmadd`
  fit in the shadow of the transcendental pipe, consistent with the [transcendental-pipe finding](../2026-10-11-transcendental-pipe/README.md)).
* So ZLUDA can use the fma-split sequence for PTX `sin` / `cos` without a throughput penalty on this hardware. `cos` adds one `fadd` (not measured separately).
* Chains of 1-9 evaluations were below the launch-overhead noise (25-35 us per dispatch): use 64 or more.

Not covered: latency of a single evaluation (the chain slope is a throughput-and-latency mix at 131,072 lanes), `cos`, `ex2` / `lg2`, accuracy
(see the transcendental findings). Not wired into `cost.rs`.

## Reproduce

`python3 scripts/run_drm_sincos_cost.py offline|hardware`; `make verify-sincos-cost` (offline, 5 checks against
[results/2026-10-18-sincos-cost](../../results/2026-10-18-sincos-cost)).
