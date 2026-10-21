# Local build patches (not pushed: ZLUDA and the LLVM fork are not pushed from this machine)

Needed to build on the M2 Max under Fedora 42 (GCC 15, aarch64), 2026-10-21:

- `llvm-agx-gcc15.patch` (Jianwen-Ding/llvm-project, branch `claude/bold-davinci-46xi9q` 3736ce1): missing includes that
  Clang/libc++ pull in transitively but GCC 15's libstdc++ does not (`StringExtras.h`, `IRBuilder.h`, `SmallVector.h`,
  `<cmath>` for `INFINITY` / `M_1_PI`).
- `zluda-aarch64-c_char.patch` (Jianwen-Ding/ZLUDA master 7a6d979): FFI strings typed `*const i8` where aarch64's
  `c_char` is `u8` (`llvm_zluda/src/ffi.rs`, `compile_agx.rs`, `utils.rs`, `ptx/src/pass/llvm/emit.rs`).
  Also run `git submodule update --init ext/HiGHS` before building `compiler` (zoc).

Build: LLVM `cmake -G Ninja -S llvm -B build -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_PROJECTS=mlir
-DLLVM_TARGETS_TO_BUILD=AArch64 -DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=AGX -DLLVM_ENABLE_ASSERTIONS=ON`, then
`ninja llc opt mlir-opt mlir-translate llvm-config FileCheck LLVMAGXCodeGen LLVMAGXAsmParser LLVMBitWriter LLVMBitReader
LLVMPasses LLVMOption LLVMLTO`; zoc: `ZLUDA_LLVM_BUILD_DIR=build cargo build --release -p compiler --no-default-features
--features agx`. With both, `agx_cuda_smoke` (no argument: PTX through zoc, plus cuLink) gives `"link_ok":true,"wrong":0`.
