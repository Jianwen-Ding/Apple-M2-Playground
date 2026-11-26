# A ragged grid's last threadgroup runs as a smaller threadgroup: SR4-6 read its own size

Status: confirmed on one device (M2 Max G14C B1), direct DRM through metal-cpp/asahi (libmetal_asahi, the
metal-cpp runtime of 2026-11-26); our own kernels compiled from AIR by the in-tree AGX backend; nothing
disassembled or decompiled.

## Claim

When the CDM global size is not a multiple of the local size (B2a: the hardware runs exactly the grid), the
last threadgroup in each such dimension is a threadgroup of the clipped size, not a full-size threadgroup with
lanes masked off:

- its threads are packed into SIMD-group lanes in order of their local position within the *clipped* shape
  (x fastest): a 1 x 8 remainder of an 8 x 8 local size is lanes 0-7 of SIMD group 0, with
  `thread_position_in_threadgroup` (0, 0) ... (0, 7);
- `get_sr` SR4, SR5, SR6 (`threads_per_threadgroup`) read the clipped size, (1, 8) there, and (8, 8) in every
  full threadgroup;
- `thread_position_in_grid` (SR80-82) and `threadgroup_position_in_grid` (SR0-2) are the same as with the full
  size: every grid position runs exactly once.

| Grid | Local | Threads run | Positions run once | SR4-5 in the partial group |
| --- | --- | --- | --- | --- |
| 33 x 17 | 8 x 8 | 561 | all | (1, 8) (x-partial), lanes 0-7 |
| 10 x 3 | 4 x 2 | 30 | all | (2, 2) |
| 40 x 3 | 32 x 2 | 120 | all | (8, 2), lanes 0-15 |

This is the semantics Metal (`threads_per_threadgroup` of a non-uniform threadgroup) and OpenCL 2.0
(`get_local_size` of a non-uniform work-group) define, so a kernel needs the *dispatch's* threadgroup size and
the grid size from elsewhere: `threadgroups_per_grid * threads_per_threadgroup` is not the grid size in the last
threadgroup (a row stride computed that way was 5 instead of 40 there, and threads wrote other rows).

## Implications

- The AGX backend's `threads_per_grid` (`threadgroups_per_grid * SR4`) was wrong in partial threadgroups; the
  backend now reads the grid size and the dispatch's threadgroup size from launch-provided uniforms
  (`llvm.agx.launch.grid`, `.agx.kernels` record extension 10), which libmetal_asahi fills.
- The AGX Performance Simulator modelled partial threadgroups as full-size ones with masked lanes (SR4-6 the
  dispatch size, lanes at full-size positions); it now runs them at the clipped size (`GroupCtx::eff_size`),
  which also changes which lanes a partial SIMD group has.

## Reproducer and evidence

`probe.cl` (built with metal-cpp/asahi `tools/air-build.sh`) and `probe.cpp` (a metal-cpp program, built like the
metal-cpp/asahi tests): every thread claims a slot with an atomic and records its grid and local positions,
threadgroup position and SR4/SR5. `METAL_ASAHI_MODE=hw ./probe` prints the table above; `METAL_ASAHI_MODE=sim`
printed (8, 8) for the partial group before the simulator fix.
