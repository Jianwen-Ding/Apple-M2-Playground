# Instruction cache beyond 12 KiB: misses grow gradually, close to random replacement and far from LRU

Status: one device (M2 Max G14C). A re-analysis of the 2026-10-20 instruction-cache records, plus real
clang-built CUDA kernels (Rodinia, through ZLUDA) replayed with `agx_run_hw --back-to-back 1000`.
Nothing new was hand-assembled or run for this note, and nothing was disassembled or decompiled.

## Claim

Take one SIMD group looping over L lines of straight-line `iadd` against the 192-line (12 KiB) cache. The fraction of
lines that miss is (ns per instruction - 0.745) / (3.09 - 0.745), using the in-cache and streaming rates from
[icache](../2026-10-20-icache/README.md), `results/2026-10-20-icache/record.json.gz`:

| loop lines / capacity | measured miss fraction | strict LRU | random replacement (whole cache) |
|---|---|---|---|
| 193 / 192 (1.005x) | 0.06 | 1.0 | 0.01 |
| 193 / 161 (misaligned, 1.2x) | ~0.39 | 1.0 | ~0.2 |
| 256 / 192 (1.33x) | 0.48 | 1.0 | 0.46 |
| 384 / 192 (2.0x) | 1.0 | 1.0 | 0.79 |

A cyclic loop larger than an LRU cache misses on every line. On this hardware the miss fraction grows gradually.
Random replacement over the whole cache matches the 1.33x point and gives the right overall shape. It
underestimates the misses at 1.2x and 2x, so the real policy lies between the two: perhaps a pseudo-LRU, or random
among the older lines.

A real kernel shows the same thing. Rodinia `hotspot` `calculate_temp` (43 x 43 workgroups of 256 threads, 202 code
lines executed, 3 workgroups resident per core, 17 waves) measures 401.7 us. Simulating its fetch through a 168-line
LRU that is emptied at every wave predicts 669 us (+66%). A 192-line random-replacement cache that keeps its lines
from the previous wave on the core predicts 406 us (+1%), and so does no refetch at all. Two more kernels that execute
code just past the capacity improve the same way: srad `srad_cuda_1` goes from +43% to +16% and particlefilter
`likelihood_kernel` from +31% to +12%.

## Implication

Code a little over 12 KiB does not fall off a cliff: going ~5% over costs a few percent of misses. When code is
trimmed for the instruction cache, every line saved helps roughly in proportion; there is no hard threshold to aim
for. Kernels several times the capacity (Cycles) stream as before.

## Caveats

- The 1.2x and 2x points disagree with pure random replacement, so the policy is not established.
- The hotspot k-sweep (38 x k workgroups, k = 1..8: 35.8 / 56 / 76 / 92.6 / 105 / 138 / 131 us) does not scale like
  the model at small k. Not explained.
- Model change and data: AGX-Performance-Simulator, branch claude/accuracy-2026-11-07,
  results/2026-11-07-held-out.
