# Workgroups along grid y run as fast as along grid x

Status: confirmed on one device (M2 Max G14C), our own kernels, commands as zluda_agx submits them. A negative result.

## Claim

The same 8192 workgroups of 256 threads take the same time whether the grid is 8192 x 1 (kernel indexing by
`%ctaid.x`) or 1 x 8192 (`%ctaid.y`): a streaming copy 186-189 us either way (~360 GB/s), and with threadgroup
memory round trips and three barriers per workgroup 182-183 us either way. The whole-transform FFT kernel of
zluda_fft_agx (threadgroup memory, barriers, 256 threads per workgroup) shows no consistent difference either
(alternating builds: 205-324 us along x, 180-312 along y; its run-to-run spread is ~25%).

## Implications

- Kernels and libraries can put a batch index in grid y without a dispatch cost; the limit is the 65535 workgroups
  per launch along y (agx_runtime's `max_grid_dim`), not speed.
- Correction to ZLUDA commit 411a3f6, whose message says the FFT kernel took 641 us with workgroups along y: that
  was one run within this spread, not the grid orientation.

## Reproducer and evidence

`results/2026-11-01-grid-orientation/{copy,tg}{x,y}.ptx`: `agx_bench_kernel copyx.ptx c --grid 8192 --block 256
--iters 500 --warmup 50 buf:33554432 buf:33554432` (`--grid 1,8192` for the y variants).
[Evidence](../../results/2026-11-01-grid-orientation/hardware.txt).
