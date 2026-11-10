# Code beyond the i-cache streams at ~31 ns per 64-byte line (warm) / ~78 ns (first fetch of the command), up to 384 KB of code; groups at the same code share the stream, and a `wait` on memory stops it (no overlap)

Status: confirmed on one device (M2 Max G14C), 2026-11-10, own probe kernel (AGX-Performance-Simulator
`scripts/probe_fetch_groups.py`) through agx_runtime (agx_run_hw `--back-to-back 1000`, top clock). 38 workgroups (one
per core) of G SIMD groups run T trips of a straight-line body of BODY_KB of independent iadds. Nothing disassembled.

## Result

- Bodies of 64-384 KB with T chosen for ~12.3k lines per run (`hardware-big-bodies.txt`): 423 / 448 / 472 / 521 /
  570 / 667 us for 64 / 96 / 128 / 192 / 256 / 384 KB. Fitting (T - 1) x W + C per line: **W = 30.6 ns per line**
  for every trip after the first, **C = 78 ns** for the first (cold) trip; W does not grow with the code size (no
  second-level code cache cliff up to 384 KB). Earlier 16-64 KB bodies: 27-33 ns per line.
- 1 and 8 SIMD groups starting together take the same time (one fetch stream serves them all); their execution
  (8 x 8 iadds per line) overlaps the stream.
- A device load + `wait` every 16 iadds adds its whole latency: 411 -> 703 us (`hardware-loads-barriers.txt`), every
  64: 483. The fetch does not run ahead while the group waits; barriers add nothing.

- Cores at different places in the code (each workgroup's start staggered by its id, `WGSTAGGER=1`,
  `hardware-core-stagger.txt`): no slowdown beyond the stagger itself (48 KB: 464 / 669 us for staggers of ~0.1 /
  0.3 ms; 192 KB: 540 / 671): no contention between cores' code streams.
- Bodies just over the i-cache (16 KB, 1.33x of 12 KiB) cost ~27 ns per line visited (331 us) although random
  replacement keeps about half the lines: isolated misses cost more than streamed ones (the simulator charges 64 ns
  for a miss whose line before was a hit, 31 for a streamed one: 356 us).

## Implications

- Big unrolled kernels (llama.cpp MMQ, tinygrad's integer-heavy reductions, Cycles) pay ~31 ns per line per pass,
  i.e. ~4 instructions per ns of straight code at best; waits inside such code are pure additions.
- AGX Performance Simulator: `AGX_FETCH_STREAM=1` (next-line stream from the previous line's arrival, restarted by
  a `wait`; first fetch at the profile's cold 70 ns, jumped-to cold lines 300 ns) (default since 2026-11-10; streamed
  lines 31 ns, isolated misses 64) reproduces the probe (48 KB: G1 412 / G8 419 vs 411 / 415; loads every 16: 665 vs 703).
