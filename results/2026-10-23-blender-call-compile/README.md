# Blender Cycles PTX compilation and AGX call/return groundwork

2026-10-23, M2 Max G14C B1 under Asahi Linux. This is a performance finding and
compiler investigation, not a completed Blender GPU render.

## Headless path

The Blender 5.1.0 ARM64 build in `/scratch/blender-5.1.0-git20260325.ae6d847d66fa-aarch64`
still needs X11 libraries at dynamic-load time with `-b`; the host does not have
them. Temporary scratch-only symbol shims let `blender -b --factory-startup`
start and enumerate `Apple M2 Max (G14C, 38 cores)` through ZLUDA's CUDA driver.
They are only suitable for this headless probe, not a packaged Blender setup.

The first 32×32, one-sample Cycles render chose the bundled
`kernel_sm_86.cubin.zst` and ZLUDA rejected it with `CUDA_ERROR_INVALID_IMAGE`.
Temporarily hiding that cubin made Cycles load its bundled
`kernel_compute_75.ptx.zst` instead. Blender's extracted PTX is 13 MiB with 75
`.entry` kernels, 383 `.func` definitions and 1,593 calls. `zoc` generated a
116 MiB linked LLVM IR file and a 46 MiB optimized IR file, then stayed at
about 100% of one CPU and 6.8 GiB RSS. It had not finished when the 600-second
render timeout expired. The cubin was restored after each attempt. No GPU render
was produced or timed.

The AGX LLVM backend explicitly runs `AGXAlwaysInline` and then the LLVM
always-inliner. `AGXTargetLowering::LowerCall` rejects surviving calls, and
the backend has no callable-function ABI. This likely makes the large Cycles
module expensive to compile; the observation alone does not isolate the exact
pass consuming the 600 seconds. B14 in the AGX Performance Simulator's
`tasks/ptx-re-blockers.md` records the measured G14C call/return behavior and
the remaining compiler work.

## First MC step and limits

LLVM's G13/G14 MC layer now recognizes the measured 6-byte direct `call`,
2-byte register `call` (`call_reg` in LLVM syntax), and 2-byte `ret` forms.
The sample `call callee; pop_exec r0l, 2; stop; callee: ret r1` assembles to
`10c00e00000052160000000088001402`; `agx_run` with
`AGX_EXPERIMENTAL_RET=buffer-pop2` completes four instructions. The simulator's
`make verify-llvm-call-ret` checks the exact bytes and control flow offline.
The LLVM MC test and existing G13 control test both pass. `agx-strict` rejects
the new instructions because Mesa does not emit them; that is expected for
this experimental path.
The playground's offline `verify-control-model` and `verify-call-ret` checks
also pass on the retained hardware records.

A first bare `agx_run_hw` run of that tiny program returned `Bad address`.
The event was recorded in the per-boot GPU safety log (1/30); an exact
known-good `stop` control completed afterward. The tiny program omits the
measured balanced mask reserve and the padding used by the retained call
probes, so the fault cannot be attributed to the new encoding or a specific
return behavior. No further unknown call program was submitted on this boot.
The MC instructions are not yet used by LLVM code generation. Needed next:
call argument and return-value placement, r1 link preservation, per-call stack
frames, register liveness, mask reserve/reconvergence, and tests against the
retained hardware corpus before enabling codegen. Call timing remains
uncalibrated in the performance simulator.
