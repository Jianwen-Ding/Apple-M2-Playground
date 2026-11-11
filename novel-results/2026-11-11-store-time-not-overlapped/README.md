# Device stores add their bandwidth time (~365 GB/s) to latency-bound kernels; DRAM-streaming kernels hide most of it

Status: confirmed on one device (M2 Max G14C), 2026-11-11. Kernels are our own compiles (clang CUDA -> PTX -> ZLUDA ->
AGX) of llama.cpp pp512 kernels, captured and replayed with agx_run_hw `--back-to-back 5000`, medians of 2 runs.
Variants are byte patches of the captured code: every `device_store` replaced by `iadd r9, r9, 0` (same size, 8
bytes), or truncated copies (a `stop` at a pc group 0 reaches once).

## Result

| kernel (pp512) | full us | no store us | + store | bytes stored | at 365 GB/s | added fraction |
|---|---|---|---|---|---|---|
| rms_norm_f32 (512 x 896 floats, xyzw stores) | 18.0 | 13.0 | +5.0 | 1.8 MB | 5.0 | 1.0 |
| cpy_scalar f32 | 78.8 | 74.0 | +4.8 | 1.8 MB | 5.0 | 0.96 |
| convert_unary f16->f32 | 4.4 | 3.4 | +1.0 | 0.26 MB | 0.7 | 1.4 |
| k_bin_bcast add (register-address store, see store-address-form) | 32.2 | 17.3 | +14.9 | 1.8 MB | 5.0 | 3.0 |
| soft_max_f32 (in place, 1 workgroup per core) | 425.2 | 403.1 | +22 | 14.7 MB | 40 | 0.55 |
| unary_gated silu (3 x 10 MB buffers, DRAM-bound) | 92.3 | 84.9 | +7.4 | 10 MB | 27 | 0.27 |
| rope_neox f32 | 33.5 | 28.3 | +5.2 | 7.3 MB | 20 | 0.26 |
| ZLUDA agx_sgemm_tile64 (16 stores per thread) | 18.8 | 15.2 | +3.6 | 1.2 MB | 3.4 | 1.06 |
| Halide stencil_chain stage_5 (4 x i16 stores per thread, 6 workgroups of 8 groups per core) | 81.4 | 70.1 | +11.3 | 12.8 MB | 35 | 0.32 |

- In latency/ALU-bound kernels (rms_norm, cpy_scalar, convert, k_bin_bcast with the uniform-form store: +5) the
  stored bytes cost their whole time at the ~365 GB/s store rate on top of the compute: stores do not overlap the
  rest of the work (also ZLUDA's sgemm tile kernel). In kernels whose loads stream from DRAM (footprint beyond the
  SLC: unary_gated, rope) only a quarter shows, and also in Halide's stencil_chain stages, whose data is in the SLC
  (16-bit stores, 48 groups per core): what decides the overlap is not known yet (not the footprint alone, not the
  store address form: stencil uses uniform base + index, cpy_scalar a 64-bit register address, both differ).
- rms_norm's `memory_barrier 1, 2, 9` after the store (and the one after its threadgroup store) cost nothing:
  replaced by `wait 0` 18.0 / 18.0 / 17.8 us (one / the other / both), so it is not a fence waiting for the stores.
- rms_norm truncation sweep (grid 131072 threads = 14 workgroups per core): stop before the index arithmetic 3.8 us,
  before the first load 7.6, after it 8.9, after the reduction 9.9, before the second load 11.0, before the store
  12.2, full 18.1. The AGX Performance Simulator matched every cut up to the store within ~5% (12.6 vs 12.1) and missed
  only the store (model 13.2 for the full kernel).
- soft_max truncation sweep (grid 262144 x 14): 54 / 101 / 125 / 165 / 277 / 327 / 377 / 396 us at trace indices
  40 / 90 / 104 / 123 / 169 / 205 / 224 / 238, no store 403, full 425. The two dependent row loads (90 -> 123) cost
  ~0.34 us per workgroup on a core (189 per core), well below two SLC latencies.

## Implications

- AGX Performance Simulator: the store bandwidth is only a GPU-wide floor (max with the compute). Tried as an
  experiment (AGX_STORE_DRAIN=8 AGX_STORE_DRAIN_ISSUE=1): a store's lines stall the core's issue at the core's share
  of 365 GB/s, except lines that already took DRAM bandwidth. It matches the llama.cpp increments (rms_norm -27 ->
  -3%, cpy_scalar -10 -> -4%, sgemm -23 -> +11%) but sends every Halide stencil_chain stage from ~-2% to ~+48% and
  nlmeans sum_s1 to +74% (held-out mean 7.6 -> 17.2%): not adopted until the overlap rule is understood.
- Code generators: in short latency-bound kernels the stores are on the critical path; fewer / wider stores help.

## Reproducer and evidence

Patched copies: `/scratch/agx-r5/r9/{nostore,rmsvar,rmstrunc,smtrunc}` (scripts `mkvar.py`, `/scratch/agx-r5/trunc.py`).
Job scripts and logs: AGX-Performance-Simulator `results/2026-11-11-sim-accuracy/hw/` (q/500, 505, 510, 515, 520).
