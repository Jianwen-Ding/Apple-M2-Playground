# Special registers: SR21 is the hardware VM slot, only SR56-59 follow divergence, and a complete compute map

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute. Every kernel used only
encodings that had already run cleanly (`get_sr`, device stores and atomic add, the emulator-gated delay loop,
`if_icmp` / `pop_exec` without jumps). The divergence kernels were also checked in the functional simulator before
they ran. 131 + 232 + 6 + 2 processes ran, with no fault, timeout or failed oracle.

## Claims

1. **SR21 is the hardware VM slot the dispatch's VM is bound to** (Mesa: `vm_slot`). It is one value for every lane
   of a dispatch, and always in **1..63** (61 distinct values seen, never 0).
   - VMs live at the same time hold different slots: 2 and 16 concurrent processes got 2 and 16 distinct values.
   - Fresh VMs created one after another take a new slot each time, cycling through 61 different slots before one
     repeats. The allocator is least-recently-used: the same order recurs across runs, and slots in use elsewhere
     (the desktop's own VMs) are skipped.
   - So it is the 64-entry UAT context table with slot 0 reserved, not a per-process or per-device counter.
2. **SR113 is a single bit (0 or 8) per dispatch, still unexplained, but now narrowed down.**
   - It is uniform over a whole 65,536-lane dispatch on all 38 cores and every hardware slot.
   - Alone, 0 of 112 submissions read 8, with short and long kernels and 1-20 submissions per process. 96
     single-submission processes, some overlapping another process's dispatch, all read 0.
   - With 12 processes submitting long kernels together, 33 of 240 read 8. Over everything, 86 of 2,648 did.
   - It changes between submissions of one process (4 processes saw both values).
   - It is not the submission index, lane, core, slot, VM slot or clock state: fast and slow (~757 / 1640 µs)
     dispatches both read 0.
3. **Under divergence only SR56-59 change.** All 256 selectors were read inside 1-3 nested `if`s with 32 / 16 / 8 /
   4 of 32 lanes active, and with one lane per quad.
   - SR56 / SR57 are the lane's rank among the active lanes of its quad and the quad's active count. SR58 / SR59 are
     the same over the SIMD group.
   - **SR16 = lane & 3** ignores the execution mask (active lanes 0, 2, 4 read 0, 2, 0).
   - **SR60 (Mesa: `coverage_mask`) = 15 and SR63 (`is_active_thread`) = 1** do not reflect the execution mask in
     compute.
   - The other 250 selectors are unchanged.
4. **Everything else reads 0.** Over 121 executing main-shader scans (2026-10-11) and the 6 divergence patterns, no
   selector outside the table below was ever nonzero.

## Compute-stage map of all 256 selectors

| SR | Value in a compute main shader | PTX use |
|---|---|---|
| 0-2 | workgroup id x, y, z | `%ctaid` |
| 4-6, 8-10 | workgroup size x, y, z | `%ntid` |
| 7 | SIMD groups per workgroup, ceil(threads / 32) | `%nwarpid`-like (per block) |
| 12, 13, 15 | imageblock width, height (0 without one), sample stride (16) | - |
| 16 | lane & 3 (ignores the execution mask) | - |
| 17 | hardware SIMD-group slot on the core (96 in the preamble) | `%warpid` |
| 18 | threadgroup memory bytes, 256-byte granule | `%total_smem_size` |
| 19 | register allocation, max(8, roundup(regs, 8)) 16-bit registers | - |
| 20 | core id, (cluster << 4) \| core | `%smid` |
| 21 | VM slot, 1..63 | - |
| 24 | program kind: 2 main, 5 preamble | - |
| 25 | 2 | - |
| 32 | USC offset of the dispatch's pipeline words | - |
| 48-50 | thread position in workgroup x, y, z | `%tid` |
| 51 | linear thread index in workgroup | - |
| 52 | lane | `%laneid` |
| 53 | SIMD group index in workgroup | warp index in block |
| 56, 57 | active rank / active count in the quad | - |
| 58, 59 | active rank / active count in the SIMD group | `popc(%lanemask_lt & active)`, `popc(active)` |
| 60 | 15 (`coverage_mask`) | - |
| 63 | 1 (`is_active_thread`) | - |
| 80-82 | global thread position x, y, z | `%ctaid * %ntid + %tid` |
| 97 | 2048 | - |
| 113 | 0 or 8 per dispatch (claim 2) | - |
| 114 | 136 | - |
| all others | 0 | - |

Still without a meaning: SR25 = 2, SR97 = 2048, SR114 = 136, SR113. No selector is a clock (2026-10-04 scan), so
`%clock` / `%globaltimer` remain unavailable in-shader.

The simulator (AGX-Performance-Simulator `rust/src/cost.rs` `GroupCtx::sr`, `func.rs` get_sr) now models every
selector but SR113. Given the launch's register allocation, VM slot and pipeline offset (`agx_run --alloc-regs
--vm-slot --pipeline`), it reproduces 253 selectors lane for lane on all 6 divergence patterns (1,518 / 1,518).
The remaining 3 are SR17 / SR20, which depend on placement, and SR113.

## Reproduce

```sh
make verify-special-registers   # offline, the retained evidence
make sr-vm-slot                 # GPU: 16 concurrent + 70 sequential VMs (~10 s)
make sr-divergence              # GPU: 6 divergence patterns x 256 selectors (~2 s)
make sr113-reps                 # GPU: SR113 per submission, alone (~1 s)
```

Evidence: [results/2026-10-16-special-registers](../../results/2026-10-16-special-registers/).
