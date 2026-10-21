# B1 (rest): ZLUDA's own scratch path on the GPU (2026-10-21)

The open part of blocker B1 (`AGX-Performance-Simulator/tasks/ptx-re-blockers.md`): `agx_runtime/src/scratch.rs` (Mesa's
helper program, the scratch layout and the Registers word's spill bucket) had only run in `drm_compute.c`. M2 Max (G14C),
ZLUDA master 7a6d979 built locally (with `notes/local-patches`), LLVM AGX fork 3736ce1 built locally, battery power.
0 faults; hang budget unchanged.

**Result: pass.** `stack.ptx` (a 1 KiB `.local` array indexed by a register, so it cannot live in registers) compiled by
`zoc --target agx --arch agx-g14c`: `stack.asm` shows `stack_adjust 268`, a 1,072-byte stack per thread, `stack_store` in
the fill loop and a `stack_load` at a data-dependent index. Checked in agx_run first (4,096 threads, 0 wrong), then
`b1_stack.rs` (a local zluda_agx bin) loads the object with `cuModuleLoadData` and launches it with `cuLaunchKernel`
(256 threads per block); zluda_agx sets up the scratch buffer and helper itself:

| Threads | Scratch (1,072 B / thread) | Wrong | Host time (launch + sync) |
| --- | --- | --- | --- |
| 4,096 | 4.4 MB | 0 | 27 ms |
| 262,144 | 281 MB | 0 | 39 ms |

So `.local` memory, `alloca` and register spills work end to end through the CUDA driver API on this GPU.
(`ZLUDA_AGX_USC_BARRIER=1` was set as for every zluda_agx run since the B42 finding.)

The full PTX -> zoc -> zluda_agx -> GPU path also passes `agx_cuda_smoke` without an argument (vectorAdd compiled from
PTX, CUDA graph, unified memory, 2D copy and two PTX modules linked with `cuLinkCreate` / `cuLinkAddData` /
`cuLinkComplete`): `"link_ok":true,"wrong":0,"graph_wrong":0,"unified":true,"unified_wrong":0,"copy2d_wrong":0`.
