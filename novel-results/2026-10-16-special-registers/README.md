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
2. **SR113 (0 / 8) is a global GPU power-management state bit, set by a ~56 ms firmware cycle while the GPU is busy
   and cleared when the GPU idles for ~1-2 ms.** This is from 41,696 timed submissions, each reading SR113 before and
   after its work (`run_sr113_reps.py --timeline`, per-submission counters via `AGX_TABLE_PEEK`).
   - **One global state.** 17,332 pairs of submissions from different processes ran at the same moment; their values
     never disagreed. The value changes *during* dispatches: 159 64-lane submissions read 0 at the start and 8 at the
     end, on all lanes. In 11 large dispatches (65,536 lanes on 38 cores) it changed on only part of the lanes,
     because lanes read it at different moments of one change.
   - **Set on a 56.0 ms grid.** The 0 -> 8 entries phase-lock to a 56.0005 ms period over an 80 s span (concentration
     0.81; shuffled controls at most 0.57). That is 7 x the 8 ms `apple,power-sample-period` the driver passes to the
     GPU firmware (M2 Max device tree). Entries land with about ±8 ms jitter within the period, and only while work is
     running. A process that is busy for 29 ms catches one about half the time (15 of 30 did).
   - **Cleared by idle.** The bit survived every GPU idle gap under 1.0 ms (64 / 64) and none over 1.8 ms (0 / 52).
     This sits just under the firmware's 2 ms idle-off delay (`idle_off_delay_ms`, driver default). With 2 ms pauses
     between submissions it only ever lasts one submission.
   - **No measurable effect on speed.** The same ALU loop takes 507.5 / 507.4 µs and the same DRAM-latency-bound
     pointer chase 429.6 / 429.5 µs with SR113 = 0 / 8. It is also independent of the GPU clock state, lane, core,
     slot and VM slot.
   - So it is most likely a flag of the firmware's power controller (for example "active / boosted" versus
     "idle-entry"), readable from shaders. Its exact meaning needs firmware documentation.
   - The fraction of time at 8 varies a lot between sessions under similar load (16-82 %), as you would expect from
     a controller state.
   - **Open anomaly:** 3 submissions (in one run of 3,840) read **60002 (0xEA62)** at the end, on all 64 lanes. None of
     19,200 later submissions reproduced it, with or without preloading the destination register. So it is still
     unknown whether this is a real SR113 value or a missed `get_sr` write.

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
| 113 | 0 / 8: global power-management state bit (claim 2) | - |
| 114 | 136 | - |
| all others | 0 | - |

Still without a meaning: SR25 = 2, SR97 = 2048, SR114 = 136. SR113 has a mechanism (claim 2) but no exact name. No selector is a clock (2026-10-04 scan), so
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
make sr113-timeline             # GPU: SR113 before / after the work, sustained and with idle gaps (~1 min)
```

Evidence: [results/2026-10-16-special-registers](../../results/2026-10-16-special-registers/).
