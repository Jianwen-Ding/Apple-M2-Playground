# Launch cost of an agx_runtime compute command, and the clock of short back-to-back commands

Status: confirmed on one device (M2 Max G14C, 38 cores, kernel 6.19.14-400.asahi.fc42.aarch64+16k), commands as
zluda_agx's agx_runtime submits them (`agx_run_hw`), firmware start/end timestamps. Measured from user space with
our own kernels; nothing was disassembled or decompiled.

## Claim

1. An empty compute kernel (`stop`, compiled by zoc from `empty.ptx`) costs **~2.3 us per command** when
   commands are queued back to back (median of the last 500 of 1000), ~3.8 us as an isolated command.
2. Beyond that, launching costs **~100 ns per workgroup per busiest core**, whether the workgroups have 32 or 1024
   threads, and whatever the register allocation (8 to 256 halves): 15,200 workgroups (400 per core) take 40.6-41.7
   us in every combination.
3. This differs from the direct-DRM harness's commands ([2026-10-11 dispatch launch](../2026-10-11-dispatch-launch/README.md):
   5.6 us fixed, 13.6 ns per SIMD group, 181 us for 16 M threads in 1024-thread workgroups) in the fixed part and
   the per-group part; the per-workgroup part agrees (94-104 ns). The command setup, not the GPU, sets them.
4. The size of the mapped memory does not change the cost (0-512 MiB mapped: 2.3-3.3 us).
5. **A few short commands do not ramp the clock.** A 26 us kernel (llama.cpp's Q8_0 matrix-vector product) takes 67
   us in the second half of 30 back-to-back commands and 26.2 us in the second half of 1000. Timing short kernels
   needs hundreds of back-to-back launches first.

## Simulator implication

`agx_dispatch --launch-profile zluda` (AGX-Performance-Simulator claude/zluda-launch-profile) uses 2.3 us / 100 ns per
workgroup / 3.2 ns per SIMD group and predicts the empty dispatches within 3-22%; `scripts/capcheck.py` times
captures 1000 back to back by default.

## Reproducer and evidence

zoc `--target air --arch agx-g14c --agx-only empty.ptx`, `.text` of the object as `code.bin`, then
`agx_run_hw code.bin --grid N --wg T --regs R --back-to-back 1000` (after `agx_run` on the simulator).
[Evidence](../../results/2026-11-01-zluda-launch-cost/launch-cost.txt).
