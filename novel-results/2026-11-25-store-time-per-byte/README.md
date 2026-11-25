# Device store time is additive and per byte (~450-520 GB/s); compute does not hide it

Status: one device (M2 Max G14C), 2026-11-25, AC power, warm (agx_run_hw --back-to-back 5000), two repeats agreeing
within 0.1 us. Our own probe kernels (AGX-Performance-Simulator `scripts/probe_hot_lines.py`), using only store
forms that ran on this GPU before. The i16 form assembles to the same bytes as the store in a Halide stencil_chain
stage (`c54c240c00c01000`). Nothing was disassembled or decompiled.

8192 workgroups of 128 threads. Each thread does two loads, a wait, an add and a store. The store cost is the time
minus the NOSTORE variant. PRE / POST add n independent iadds before the loads / after the store.

| Store cost (us) | PRE 0 | PRE 256 | PRE 1024 | POST 256 | POST 1024 |
|---|---|---|---|---|---|
| i32, 4.2 MB | 10.1 | 8.1 | 8.0 | 5.7 | 6.7 |
| i16, 2.1 MB | 5.2 | 4.4 | 4.6 | | |

- At PRE 1024 the kernel is compute-bound (170 us), yet the 4 MB of stores still add 8 us. Store time does not overlap
  with ALU work.
- Half the bytes cost half the time. The cost is per byte written, not per store instruction.
- This updates [store-time-not-overlapped](../2026-11-11-store-time-not-overlapped/README.md). The Halide stencil's
  "two-thirds hidden" store time fits once the bytes are counted, not the 64 B segments its partial-line stores
  touch. Its 4 i16 stores per thread rewrite segments the core already wrote, and in a write-back cache those
  rewrites leave memory once.

## Implication

- **Compiler:** stores cost their bytes on top of everything else. Narrow output types and in-place accumulation in
  registers rather than in memory pay off directly.
- **Simulator:** charge stores by distinct bytes, not by segments, and do not hide them behind compute
  (AGX-Performance-Simulator results/2026-11-25-store-drain).
