# A dependent chain of first touches costs ~300 ns a hop whoever wrote the lines and however wide or sequential the hops are

Status: confirmed on one device (M2 Max G14C), our own kernels, commands back to back as zluda_agx submits them.

## Claim

Extends [first-touch-pages](../2026-11-01-first-touch-pages/README.md) (one thread, a new line per hop: 23.7 us for
64 hops). Two candidate explanations for kernels that read new lines faster than that were tested and refuted:

- **Lines the GPU wrote in the previous command are not faster.** A chase that stores into each line it visits (so
  the next command chases lines the GPU just wrote) takes 24.9 us; the control, storing to other lines, 25.0 us.
  Consistent with command boundaries invalidating L2 ([l2-command-boundary](../2026-10-16-l2-command-boundary/README.md)):
  written lines are not kept close either.
- **No stream prefetch for a dependent chain.** A SIMD-group chase whose hops cover 64, 128 or 256 bytes, sequential
  or 4 KiB apart, takes 21.8-26.0 us (64 hops: ~300-370 ns each beyond the launch). Wider hops cost slightly more,
  sequential ones are not cheaper.

## Implications

- For a few groups waiting on new lines, ~300 ns per dependent wait is the number to use (about the simulator's SLC
  latency; its zluda profile's L2 rule gives ~120 ns and is 50% fast on all nine probes).
- Kernels measured faster than that on new lines (ZLUDA's Jacobi round: 16 waits a group in 5.2 us of work) need
  another explanation; neither data written by the GPU nor sequential access is it. Open.

## Reproducer and evidence

`results/2026-11-01-gpu-written-lines/chasew.ptx` (kernels `chasew`, `chases`) and `chasev.ptx`; commands and numbers
in [hardware.txt](../../results/2026-11-01-gpu-written-lines/hardware.txt). Simulator side: AGX-Performance-Simulator
results/2026-11-01-latency-chain-captures.
