# B40: the simulator's whole-dispatch model against the hardware on ZLUDA's library kernels (2026-10-21)

Blocker B40 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), **battery power**. The 11 `agx_libs`
fat objects (blas, blasc, conv, dnn, epilogue, fft, hgemm, rand, sgemm, solver, sparse) built from ZLUDA master 7a6d979
with the LLVM AGX fork 3736ce1 (both local, `notes/local-patches`). ZLUDA's `agx_libs/kernels/test_kernels.py` ran every
case with `run_and_predict.py` as its `--agx-run`: each launch runs on the GPU through `agx_run_hw` (results and dumps,
so test_kernels checks correctness) and is predicted by the simulator's `agx_dispatch` with the same uniforms and memory.
`agx_run_hw` gained a local `--repeat N --warm-ms M` (re-run from the same initial memory until M ms of GPU time have
run; report the minimum), because a single cold launch runs at a low clock (first / warm = 1.2-1.5x).

## Correctness: 817 of 819 cases correct on the GPU

All cases first passed in agx_run. On the GPU every case of every library is correct except `sgemm tile64` (2 cases):
`agx_sgemm_tile64` spills (17 `stack_*` instructions) and `agx_run_hw` sets up no scratch memory, so the command
faults (zero timestamps). Through zluda_agx, which sets up scratch (B1), this kernel gets its stack; `agx_run_hw` should
reject or support stack-using kernels.

## Time: measured / predicted (1,538 launches, warm minimum; `analysis-warm50.txt`, `launches-warm50.jsonl.gz`)

| Library | Launches | Median warm time | Median predicted | Median ratio | p10 | p90 |
| --- | --- | --- | --- | --- | --- | --- |
| blas | 224 | 15.0 us | 7.8 us | 2.08 | 1.17 | 3.71 |
| blasc | 278 | 23.8 | 8.9 | 2.26 | 1.27 | 7.09 |
| conv | 36 | 34.1 | 11.3 | 3.04 | 2.69 | 3.79 |
| dnn | 136 | 16.7 | 6.8 | 2.50 | 2.00 | 3.81 |
| epilogue | 10 | 7.4 | 6.5 | 1.16 | 1.14 | 1.21 |
| fft | 76 | 11.3 | 6.7 | 1.69 | 1.04 | 4.98 |
| hgemm | 8 | 30.9 | 11.6 | 2.27 | 1.37 | 3.17 |
| rand | 10 | 10.2 | 6.1 | 1.67 | 1.35 | 11.07 |
| sgemm | 8 | 24.5 | 10.0 | 1.95 | 1.38 | 3.50 |
| solver | 424 | 13.2 | 7.0 | 1.87 | 1.04 | 5.75 |
| sparse | 328 | 11.5 | 7.5 | 1.55 | 1.05 | 3.65 |
| **all** | **1,538** | | | **2.02** | **1.08** | **4.97** |

By measured duration: launches under 10 us (launch overhead dominates) **1.15**; 10-50 us **2.05**; over 50 us **4.63**.
The model underestimates, increasingly with kernel length. Worst outliers: a `rand` launch of one 32-thread workgroup
(253 us measured, 23 us predicted, 11x) and a `blasc` kernel of one 16x4 workgroup (~232 us vs ~26 us, 8.8x): long,
latency-bound runs on one core.

**Caveat: battery power.** On battery, sustained load runs the GPU about 2.1x below its top clock
(`novel-results/2026-10-16-battery-clock-states`), while `agx_dispatch` assumes 1,398 MHz. The growth of the ratio with
duration fits that, so part of the long-kernel error is the clock state and part is the model; repeat on AC power (or
pass the measured clock with `agx_dispatch --clock`) before tuning. Short launches (1.15) are already close.

The cold first-run times are kept too (`launches-cold.jsonl.gz`: median ratio 2.6). The f64 kernels of
`ptx/tools/agx_f64_check.py` were not run separately; the `d`-variants inside blas / solver / sgemm cover software f64.
