# New pages cost a command no more than new cache lines (no visible translation penalty at first touch)

Status: confirmed on one device (M2 Max G14C), commands back to back as zluda_agx submits them; our own kernel.

## Claim

One thread making 64 dependent loads, each command starting with the caches and translations it inherits from the
previous one: a new 64-byte line per hop costs 23.7 us per command, a new 16 KiB page per hop 24.2 us (+8 ns per new
page), the same line every hop 8.8 us. A dependent load to a line not in the GPU's caches costs ~237 ns more than an L1
hit at the warm clock; touching a new page adds almost nothing on top.

## Implications

- Small kernels on the AIR route that take 2-6 us longer than the simulator predicts (llama.cpp's rope, rms_norm,
  set_rows: AGX-Performance-Simulator results/2026-11-01-llama-air-captures) are not paying page walks or cold-line
  latency the model lacks: the model is within +13% on these chases (-12% on the L1 one).
- No reason to pack a kernel's small buffers into one page for translation's sake.

## Reproducer and evidence

`results/2026-11-01-first-touch-pages/chase.ptx`: `agx_bench_kernel chase.ptx chase --grid 1 --block 1
buf:1048640 u32:64 u32:STRIDE buf:64` with `ZLUDA_AGX_CAPTURE`, the capture replayed with `agx_run_hw --back-to-back
1000`. [Evidence](../../results/2026-11-01-first-touch-pages/hardware.txt).
