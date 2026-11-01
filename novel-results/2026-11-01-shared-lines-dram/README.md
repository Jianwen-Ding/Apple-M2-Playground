# Lines read by neighbouring workgroups on different cores cost DRAM bandwidth once

Status: confirmed on one device (M2 Max G14C), our own kernel through ZLUDA's AIR route, back to back.

## Claim

Column sums over buffers far beyond the system-level cache (64 / 256 MiB), 27 workgroups of 64 a core: with each
SIMD-group reading its own two columns, 197 / 739 us; with group t reading columns t and t + 1 (every column read by
two neighbouring groups, mostly in different workgroups on different cores), 109 / 383 us: 0.52-0.55x. Both stream
~350-363 GB/s of distinct data: the second core's read of a line comes from the GPU-wide caches, not DRAM.

## Implications

- Stencils and overlapping tiles do not pay DRAM bandwidth for the overlap even across cores; only distinct bytes
  count against the ~360 GB/s.
- AGX Performance Simulator: DRAM traffic is now divided among neighbouring workgroups that read the same lines
  (`dram_share`); image_rotate and canny_nonmax_suppression went from +22 / +21% to -5 / -3%.

## Reproducer and evidence

`results/2026-11-01-gpu-written-lines/colsum.ptx` (kernels colsum, colsum_overlap);
[hardware.txt](../../results/2026-11-01-gpu-written-lines/hardware.txt).
