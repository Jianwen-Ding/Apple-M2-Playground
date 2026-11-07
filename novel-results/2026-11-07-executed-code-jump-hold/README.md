# The forward-jump scheduler hold follows the code a kernel runs, not its size; short-kernel times need a warm clock

Status: one device (M2 Max G14C). The data comes from real clang-built CUDA kernels (Rodinia hybridsort, llama.cpp
token generation) captured through ZLUDA and replayed with `agx_run_hw --back-to-back 1000`. The geometry was changed
with `--grid`. Nothing was hand-assembled for this note, and nothing was disassembled or decompiled.

## 1. Taken forward jumps in a large program whose executed path is small

The AGX-Performance-Simulator charged every taken forward jump a 33-cycle scheduler hold when the program was
larger than 16 KiB. That hold was fitted to 40 KB straight-line probes, which are bound by instruction fetch
([2026-10-20 fp32-ieee](../2026-10-20-fp32-ieee/README.md)). Rodinia hybridsort's `mergeSortFirst` is 28 KB of code
because ZLUDA emulates `tex1Dfetch` in software, but its groups execute only 72 lines (4.6 KB). It takes 144 register
halves, so 2 workgroups of 256 threads (16 SIMD groups) fit on a core.

| grid (threads) | waves per core | hw (us) | model, hold by program size | model, hold by executed lines |
|---|---|---|---|---|
| 9,728 (1 wg per core) | 1 | 16.4 | 13.5 | 12.3 |
| 19,456 | 1 | 21.8 | 13.7 | 12.3 |
| 77,824 | 4 | 40.5 | 37.2 | 28.3 |
| 311,296 | 16 | 110.8 | 132.7 | 97.1 |
| 1,049,088 (captured) | 54 | 317.5 | 438.9 (+38%) | 318.7 (+0.4%) |

In steady state each extra wave costs 5.4-5.9 us on the hardware, against 8.0 us with the hold and 5.7 us without.
The executed path stays in the 12 KiB instruction cache, so the jumps are not fetch-bound. The simulator now
decides the hold from the executed lines (still at 16 KiB). An executed-lines threshold of 12 KiB was tried and was
worse: Halide local_laplacian/compositing `output` went from +20% to +117%.

The first wave is slower than the model: 16-22 us measured against 12 us predicted. That fits a cold 28 KB program
fetched at the start of each command, but this note does not separate the causes.

## 2. Re-read lines are cheaper than first touches (model inference)

A wave of a kernel that re-reads data other cores or earlier waves have already read (Halide bilateral_grid's slice,
local_laplacian pyramid levels) runs faster than a model that charges every line the wave meets for the first time
as new: 300 ns, at the DRAM rate. The model now charges as new only the fraction footprint / (sum over waves and
cores of each wave's lines), with the footprint capped by the buffer sizes. It gives the rest L2 latency, consistent
with the GPU-wide L2. Over 159 held-out launches the median error fell from 9% to 7%, and bilateral_grid went from
+53% to +27%. This is a fit to real kernels, not a direct measurement of the L2.

## 3. Short llama.cpp kernels: 300 back-to-back commands are not enough

The same captures (llama.cpp Qwen2.5-0.5B Q5_K_M, token generation) were timed twice. One run used
`--back-to-back 300` while other GPU jobs were running. The other used `--back-to-back 1000 --hw-repeat 5` on an
idle GPU.

| kernel | b2b 300, busy | b2b 1000 x5, idle |
|---|---|---|
| mul_mat_vec_q Q5_1 (grid 224) | 35.3 us | 19.0 us |
| mul_mat_vec_q Q8_0 (grid 32) | 23.5 | 17.2 |
| mul_mat_vec_q Q5_K (grid 896) | 38.5 | 29.6 |
| mul_mat_vec_q Q6_K (grid 896) | 45.3 | 30.2 |
| rms_norm | 7.6 (9.0 once at 1000 x1) | 5.5 |

Kernels of 5-50 us need >= 1000 back-to-back commands and a quiet GPU, and a single run of a < 10 us kernel varies
by up to 1.6x. With the good times, the simulator's median error on these 10 launches is 9-10%, not 29%.
