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

## Opt-in LLVM leaf-call code generation, 2026-10-23 follow-up

LLVM now has `-agx-experimental-leaf-calls` for a deliberately narrow case:
a direct call from an AGX kernel to a `noinline`, argument-free, void leaf
function. The callee may use intrinsics but has no ordinary calls or allocas.
The compiler reserves r1 for the link, emits a direct `call`, and follows it
with `pop_exec r0l, 2`. The leaf emits `ret r1`. The default inlining path is
unchanged; the flag is required. This is the first LLVM IR call that reaches
AGX instructions rather than being inlined or rejected.

The fixture `llvm/test/CodeGen/AGX/experimental-leaf-call.ll` builds with
`-verify-machineinstrs`. Its `.text` begins `10c01e000000` (`call leaf`),
`521600000000` (`pop_exec r0l, 2`), `8800` (`stop`). The leaf return is
`1402`. `AGX-Performance-Simulator/scripts/verify_llvm_leaf_call.py`
compiles that IR to an object, checks the bytes and target offset, then
replays the exact code with `AGX_EXPERIMENTAL_RET=buffer-pop2`; it executes
nine instructions and stores the expected `7` at address 4096. This is an
offline functional check, not a hardware validation or timing result.

That first emitted call had no pre-call mask reserve, full register-preservation
ABI, nested-link save, or separate per-function stack frames. Only the
full-mask, entry-call fixture has been checked in the simulator. Do not enable
the flag for Blender or Geekbench benchmarks: a successful compile would not
establish correctness. The earlier bare hardware call fault remains
unexplained. No additional hardware call sequence was submitted.

### Balanced mask reserve follow-up

The next compiler iteration now emits `if_fcmp r0l, eq, 0.0, 0.0, 2`
(`push_exec r0l, 2`) immediately before the direct call, followed by the
existing `pop_exec r0l, 2` after return. The initial six bytes are
`421000000000`; the compiler-generated sequence passes the same simulator
store check in ten instructions. This matches the measured balanced reserve rule for masked
callers. The entry-only call restriction remains, and this offline check
still does not establish hardware safety or general ABI correctness.

### Scalar ABI and caller liveness follow-up

The opt-in path now also passes one i32 argument and one i32 result in r2
for single-block leaf functions.
Calls carry an empty preserved-register mask so LLVM spills caller values
that remain live across the call. AGXInsertWaits drains pending asynchronous
loads before the call. The retained scalar fixture loads 42, calls a leaf
that adds 5, then adds the original 42 to the returned 47. The simulator
checks the final 89, including a caller spill and reload. The no-argument
fixture still checks a side-effecting void leaf. Separate callee stack frames,
larger signatures, and hardware validation are outstanding. The backend
rejects a non-kernel stack frame under this option to avoid overlapping the
caller's saved values.

### Wider ABI, masked calls and separate leaf frame follow-up

The opt-in ABI now uses r2..r29 for up to 28 legalized 32-bit argument slots.
i64 values take an aligned pair; arrays are split into their scalar parts.
An aggregate fixture passes i64, `[3 x i32]` and i32 and returns `[3 x i32]`;
the simulator checks 15, 23 and 31. A 32-lane fixture calls a divergent
multi-block leaf from a masked caller and checks every output across the
call/skip split. The backend no longer resets r0l at callable entry, keeps
the return-side `pop_exec r0l, 2` immediately after `call` through scheduling
and register allocation, and waits for pending loads before the call.

One non-nested leaf may now use its own 4 KiB scratch region starting at byte
offset 4096, while the kernel uses offsets below 4096. The kernel reserves
both regions with `stack_adjust`; larger caller or callee frames are rejected.
A compiled caller/callee-spill fixture uses offsets 8 and 4096 respectively,
and the simulator returns 127 from input 42. These are offline functional
results. The earlier hardware fault is still unexplained, and call timing
remains uncalibrated in AGX-Performance-Simulator.
