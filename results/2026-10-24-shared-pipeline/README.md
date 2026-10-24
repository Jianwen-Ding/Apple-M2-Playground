# Shared pipeline optimization checkpoints

M2 Max, Asahi Linux, 2026-10-24. The continuing objective is to reduce costs
throughout the PTX → LLVM → AGX → DRM pipeline while checking Geekbench,
Blender, llama-app and the performance simulator. This report distinguishes
measured improvements from unchanged or incomplete results.

## Pushed changes

* LLVM `07a2e4f1702f`: prune unreachable device-function chains before forced
  inlining. Follow-up `68a9f8397e97` strengthens the regression check range.
* LLVM `a6fc58f02bcc`: compute uniformity only when variable-index shuffles
  need it, after any shuffles introduced by matrix lowering.
* ZLUDA `ed757a8`: per-entry cache locks prevent duplicate concurrent
  compilation and conflicting temporary-file writes. Warm hits do not lock;
  different keys stay independent; unavailable caches still allow compilation.
  The source digest is computed once across miss/recheck/write.
* Simulator `7b0ab0f`, `4ca91e6`: matching compiler fixtures, functional/cost
  checks, native and emulated matrix-lane checks, and reproducible results.
  No decoder or hardware-cost parameters were changed.

## Evidence and limits

Blender camera-only optimized IR: alternating three compilations per variant
give median wall times 0.6572 → 0.4134 seconds with early pruning (37.1%
less). The six generated `.text` sections are identical, 44,222 bytes,
SHA-256 `48252ea19c0650f3a52e3011fa461e42f44df469d7d5964a8eabb9fa17c694ba`.
See `camera-timing.json` and `camera-code.json`.

Blender surface-only optimized IR: one paired compile stopped before
`structurizecfg` takes 36.865 → 31.689 seconds with conditional uniformity.
Backend pass time is 21.105 → 15.886 seconds, including removal of a
4.515-second uniformity analysis. Both intermediate IR dumps are identical;
their size/hash are retained in `uniformity-stage-comparison.json`. These
are partial compilation measurements, not render speedups. Complete shader
compilation still exceeded 150 seconds in the separate cleanup experiment.

Geekbench 7.1.0 ARM64: the early-pruning off/on runs reach all eleven GPU
workloads and then fail the network upload. No published score is available.
They have the same 11 resource-limit rejections during launch-size tuning.
The API-recorded interval is 128.650/129.025 seconds, with 2,026 compiler
invocations in each and aggregate compiler-process time 154.734/153.993
seconds. Compiler processes overlap; their sum is not application wall time.
The profiled GPU sums are 25.354/26.041 seconds. This pair does not demonstrate
a Geekbench speedup. See `geekbench-comparison.json`.

llama-app b11706, supplied Qwen GGUF: four alternating cold-cache runs with
specialization disabled all match the same executable's CPU counting output
and exit 0. Early pruning does not show a measurable benefit in these runs:
the wall times remain about 17.6 seconds, with 39 compilations per run.
See `llama-pruning.json`. After both pushed compiler changes and the cache
fix, the warm counting run exits 0, matches CPU, takes 2.038 seconds, has
39 cache hits and invokes no compiler (`pipeline-warm-qwen.json`). This
cold/warm difference is not an isolated optimization speedup.

Correctness gates pass: 77 LLVM AGX code-generation tests, 47 AGX runtime
tests, 33 CUDA driver tests, and 99 simulator tests. The simulator's early
pruning fixture produces identical live code, output 42, execution counts
and predicted cost on G13G/G14C. The matrix-lane fixture checks 192 float
elements across G13G emulation, G14C emulation and G14C native matrix code;
all match its independent row-sum reference. The rebuilt compiler's GPU
smoke test has zero wrong results over 50,000 elements, including its graph,
unified-memory and 2D-copy cases.

The cache concurrency regression launches eight simultaneous misses and
requires exactly one compiler callback. Separate checks cover compilation
failure/retry and an unavailable cache. This proves deduplication behavior;
application-level cache-concurrency savings have not yet been isolated.

## Reproduction and next work

LLVM build source is staged under `/scratch/llvm-agx`; authoritative tracked
source is `../llvm-project`. `/scratch/llvm-agx-build/bin/llc` and the deployed
`/scratch/geekbench-extract/cargo-target/release/zoc` contain the pushed
changes. Frozen earlier compilers, logs and regenerable objects are under
`/scratch/agx-shared-optimization`. The 1.19 GB intermediate IR dumps were
removed after hashing to preserve disk space.

Use `ZLUDA_AGX_LLVM_ARGS=-agx-prune-before-inline=false/true` for the early
pruning A/B switch. Simulator checks are `scripts/verify_llvm_pruning.py`
and `scripts/verify_llvm_shuffle_analysis.py` in the simulator repository;
their result reports document LLVM and simulator tool overrides.

The post-inline InstCombine/SimplifyCFG experiment was discarded: it left
the camera live code unchanged and the surface compile timed out after
150 seconds both ways. No unvalidated cleanup pass remains enabled.

At this checkpoint, a third Geekbench run with both compiler changes and
the cache fix is active, writing `geekbench-pipeline.*` in scratch. Next:
finish that comparison, investigate loop-exit normalization/structurization
on the large Blender shader, and look for shared runtime/GPU execution
improvements. Graph batching stays disabled by default because the earlier
Qwen correctness tests demonstrated corruption with it enabled. The goal
remains active; faster full Blender rendering and gains for every workload
are not established here.
