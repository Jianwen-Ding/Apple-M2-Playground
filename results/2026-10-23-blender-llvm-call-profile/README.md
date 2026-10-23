# Blender Cycles PTX call-shape and compile profile

M2 Max, Asahi Linux, 2026-10-23. This is offline analysis of Blender 5.1's
bundled `kernel_compute_75.ptx.zst` after decompression. No GPU call sequence
was submitted and no render or Metal comparison was produced.

Input: `/scratch/blender-ptx-only/module.ptx`, 12,978,351 bytes, SHA-256
`e8563d518b04e9ce7d12fb03225b462fd9bc4b87ef59717941c1c6e4c9ee0858`.
The ZLUDA `zoc --target agx --arch agx-g14c` run wrote its unoptimized and
optimized LLVM IR to `/scratch/blender-ir-profile/` before code generation
was stopped. `module.ll` is 119,804,859 bytes, SHA-256
`961597c6e9b3abf474fc5c1ecc5d8d8ae54606166616391e602736a1aec5a290`;
`module.opt.ll` is 47,548,867 bytes, SHA-256
`fd2d7f19e245225cd7716b2951d340c059dae4bf97fcbd342bfe8e845da7e23c`.
These scratch files are regenerable and are not version controlled.

The PTX has 297 defined functions plus 86 repeated declarations. The
unoptimized LLVM IR has 372 function definitions and 2,120 direct
non-intrinsic call sites: 1,593 user-function calls and 527 ZLUDA helper
calls. Optimized LLVM IR still has 372 definitions and 963 user-function
call sites. The largest user callee at that point has 64 sites. Counts were
obtained from `define` and direct `call ... @name(` lines; indirect calls and
intrinsics are excluded from the call-site totals.

LLVM function definition arities before code generation are:

| Arguments | Functions |
|---:|---:|
| 1 | 4 |
| 2 | 61 |
| 3 | 93 |
| 4 | 65 |
| 5 | 70 |
| 6 | 28 |
| 7 | 13 |
| 8 | 2 |
| 9 | 17 |
| 10 | 15 |
| 13 | 2 |
| 14 | 1 |
| 18 | 1 |

None of the four one-argument definitions takes an i32: two take i64, one
takes `[4 x i32]`, and one takes a by-reference pointer. The current
`-agx-experimental-leaf-calls` ABI (at most one i32 input and output) thus
cannot keep any of these Blender functions out of the forced inliner. A
useful Cycles call ABI must handle multiple scalar arguments, i64/pointers,
aggregates and separate per-function stack frames. This is a direct reason
to prioritize a general ABI before claiming a Blender compile-time gain.

The ZLUDA PTX translation passes visible in the log each took under 0.5 s;
the run reached `module.opt.ll` and was stopped before it emitted assembly.
It does not isolate one LLVM pass as the cost of the long compilation. The
earlier headless Blender attempt still exceeded 600 s in `zoc` with no render.
