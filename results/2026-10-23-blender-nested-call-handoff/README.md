# Blender nested-call compile handoff

M2 Max, Asahi Linux, 2026-10-23. This is an unfinished experimental compiler
step; no Blender render, hardware execution of compiler-generated nested
calls, or Metal performance comparison was completed in this step.

## Why this was attempted

The Cycles surface kernel has a direct device-function call tree with a
longest observed path of six edges. The previous opt-in LLVM AGX ABI only
kept leaf functions as calls. Its always-inliner expanded the surface kernel
to roughly 354,000 IR lines and 22,500 basic blocks. StructurizeCFG alone
took 93.1 seconds on the surface-only optimized IR. Details and earlier
Blender probes are in
[the lazy-kernel report](../2026-10-23-blender-lazy-kernels/README.md).

## Changes in progress

The opt-in `-agx-experimental-leaf-calls` path now permits eligible nonleaf
device functions. Before inlining wrappers, the AGX pass computes a
conservative static call depth from kernel entries, capped at seven edges.
Each depth uses a distinct 4096-byte scratch region; the kernel reserves the
whole stack once. A nonleaf callee saves its incoming `r1` link in a reserved
register indexed by depth and restores it before returning. The call lowering
accepts direct calls from nonkernel functions. The option name is historical.
The default compilation path is unchanged.

The LLVM fixture `experimental-nested-call.ll` compiles a kernel calling a
middle function that calls a leaf. It checks `stack_adjust 3084`, link save
and restore, and the leaf's frame at byte offset 8192. The simulator's
`verify_llvm_leaf_call.py` compiles and replays the same fixture, checking
the final value 13. The AGX codegen suite passed 74/74 tests, and the
simulator's call fixtures passed. This establishes an offline functional
check for that simple two-level chain only.

## Next session

1. Run a divergent nested-call fixture with spills at every depth through
   the simulator. Inspect the generated call/return ordering and reserved
   register liveness in machine IR.
2. Run the staged hardware handoff checks in
   [call/return probing notes](../../notes/call-return-handoff.md) before any
   compiler-generated nested-call GPU submission. Do not infer hardware
   safety from the simulator replay.
3. Compile the exact saved Cycles surface-only IR with and without this
   opt-in change. Measure optimized function count, StructurizeCFG time,
   full `llc` time, object size, and resulting register/stack use. The
   extracted IR is in scratch at
   `/scratch/blender-ir-profile/module.surface-only.ll`.
4. Check whether `AGX::usesGlobalData` and call-signature limits still force
   the largest Cycles functions to inline. If so, profile those blockers
   before expanding the ABI. Check for any regression in function metadata:
   even the earlier one-level call fixture reported 128 GPRs on the calling
   kernel, so this is not yet a measured nested-call regression.
5. Only after correctness checks, rebuild ZLUDA against the changed LLVM,
   try headless Blender, and compare completed workloads to Metal. Geekbench
   has not been revisited in this step. The simulator's call timing is still
   uncalibrated and must not be used as a performance claim.

The opt-in depth analysis is conservative and currently falls back to
inlining eligible functions if its observed graph exceeds seven edges. The
scratch ABI limits each function frame to 4096 bytes. Recursion and indirect
calls remain outside this experimental path.
