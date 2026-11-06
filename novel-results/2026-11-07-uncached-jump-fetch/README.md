# A taken jump to an uncached code line costs ~235-325 ns; straight-line code ~70 ns per line

Status: one device (M2 Max G14C), one run each, our own hand-assembled kernels (iadd, jmp_exec_any, stop; no calls) through
agx_run_hw, back to back. Nothing was disassembled or decompiled. Two GPU faults of another process fell inside these runs
(see Caveats): do not repeat on a GPU another job is using.

## Claim

One SIMD group runs N one-line blocks (7 `iadd` + `jmp_exec_any` + filler = 64 bytes) once per command, so each line is
fetched cold (the instruction cache does not survive the command boundary, [code fetch](../2026-11-01-code-fetch/README.md)):

| Code shape | ns per block (slope 1024 -> 8192 blocks) |
|---|---|
| straight: 8 `iadd` per line, no jump | **70** per line (matches the 8.85 ns per 8-byte instruction streaming rate) |
| each block jumps to a random other block | **235** |
| each block jumps to the next line | **324** (more than a random target: not explained) |
| 4-line blocks, random jump at the end | 451 (= 3 x 70 + ~240) |

So a taken jump whose target line is not cached costs about **165-255 ns more than falling through** to the next line: no
prefetch follows a jump, and sequential prefetch does not help a jump to the next line either.

Related: stack loads (`stack_load; wait 0` with the word stored P words earlier, one group, 16 KB frame) cost 103 ns per loop
iteration up to 8 KB of 128-byte rows (L1), 161 ns at 32-128 KB (L2) and 648 ns at 512 KB, consistent with the
interleaved layout of [stack memory](../2026-11-01-stack-memory/README.md) and the device-load latencies.

## Implication

Large branchy kernels (Blender Cycles shading: 1.8 MB of code, 120-200 KB executed by one SIMD group, 10-17x the 12 KiB
[instruction cache](../2026-10-20-icache/README.md)) refetch lines all the time, and every jump into a line that was evicted
costs a DRAM-like latency that a lone group cannot hide. One path of `shade_surface` runs 876 us on the GPU for 34,000
instructions (36 cycles per instruction). Compiler: smaller hot code (less inlining of rare paths, cold code moved out of
line, fewer taken branches) and higher occupancy, so other groups run while one waits for its fetch.

## Caveats

- Bimodal timings: some runs land in a state 1.5-2x slower (clock or power state); the table uses the lower, repeated values.
- The 21:28 / 21:29 faults (unmapped reads at 0x1000004100 / 0x1100004000, gCDM_CS) came while Blender ran on the GPU and
  this probe ran; the probe's jump targets are all inside the code (the emulator runs exactly the expected count), but its
  first version had no padding after the code. It now appends 16 KB of `stop`. Cause not established.
- Code beyond the cache fetched in the same command (reuse at L2) was not separated from cold fetch here.

## Reproduce

AGX-Performance-Simulator `scripts/probe_jump_fetch.py [hw|sim|both]` and `scripts/probe_stack_latency.py`, on an idle GPU,
after `gpu_safety.py status`. [Evidence](../../results/2026-11-07-uncached-jump-fetch/hardware.txt).
