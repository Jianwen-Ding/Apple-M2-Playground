# ZLUDA issues found during hardware exploration

Notes for Jianwen-Ding/ZLUDA (`master` after PR #1). Nothing here has been pushed to ZLUDA.

## 2026-10-20

1. **zluda_agx does not build on aarch64** (the Asahi machine itself). `c_char` is `u8` on aarch64:
   `format/src/lib.rs` implements `CudaDisplay` for `Option<unsafe extern "C" fn(*const i8)>` and
   `fn(i32, *const i8, *const i8)`, and `zluda_agx/src/bin/agx_cuda_smoke.rs` uses `[0i8; 128]`.
   Fix: use `std::ffi::c_char` (3 lines; `results/2026-10-20-b2-hw-runner/zluda-aarch64-c_char.patch`).
2. **agx_runtime has no scratch support** (`helper` is always zero). Kernels that spill or use `.local` need, per
   `results/2026-10-20-b1-direct-drm-scratch`: Mesa's `libagx_helper` binary in the USC heap (tagged address | 1),
   a scratch buffer with Mesa's header/blocklist layout (128 subgroups per core), `helper.data` = header VA, and the
   USC Registers word's Spill size (bits 18..21) = 1 + ceil(log2(ceil(dwords / 8))). Ship the helper bytes
   (`helper-mesa.bin`, from Mesa 25.3.6) or build them from Mesa's `libagx/helper.cl`.
3. **Soft faults are on** (`features` = 1 on this M2 Max): out-of-bounds loads return 0 and stores are dropped
   without a failed fence, so `CUDA_ERROR_ILLEGAL_ADDRESS` cannot come from the fence status for these.
4. **Uniform words can carry 64 halves, not 32** (`agx_runtime/src/lib.rs` `UNIFORM_WORD_HALVES = 32`), and halves
   256..511 need the 0x3d "Uniform high" tag (`usc_words` asserts start < 256). Measured on the M2 Max:
   `results/2026-10-20-b9-uniform-preload` (the full 512-half file works).
5. **Faulting kernels report success.** Instruction faults (undecoded opcode, jump into unmapped USC space) complete
   with sync-file status 1; only the command timestamps stay 0. `agx_runtime` should zero the timestamp slots before
   each submit and turn "fence ok but start == end == 0" into `CUDA_ERROR_LAUNCH_FAILED`
   (`results/2026-10-20-b20-failed-jobs`). Out-of-bounds stores are silently dropped (soft faults).
6. **Cooperative launch limit.** A whole grid is reliably co-resident only up to about 38 x min(15, floor(S/g) - 1)
   workgroups (`results/2026-10-20-b5-coresidency`), well below occupancy x cores. The TMEM slab pool (B30) and any
   `grid.sync()` emulation must cap CTAs in flight to that; non-resident workgroups start only when others exit.
7. **Intra-warp spin deadlocks** (`results/2026-10-20-b4-simd-forward-progress`): the `if` side of a divergent
   SIMD group runs to completion before the `else` side; report pre-Volta scheduling or rewrite such spins.
