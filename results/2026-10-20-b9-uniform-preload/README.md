# B9 (and B2b): uniform preload limits on the M2 Max (2026-10-20)

Blockers B9 and B2b of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: the whole 512-half
uniform file preloads correctly, in Mesa's 64-half words, with no measurable launch cost.**

`tests/drm_compute.c` gained `AGX_UNIFORM_HALVES=N`: halves 0..N-1 are preloaded (32-bit uniform k =
0xA0000000 | k, with u4..u9 the harness's usual values), split as Mesa's `agx_usc_uniform`
(`src/asahi/libagx/libagx_dgc.h`): at most 64 halves per USC Uniform word (64 encodes as 0 in the 6-bit size field),
tag 0x3d "Uniform high" with start & 255 for halves 256..511, and CDM launch word 0 uniform count =
ceil(N / 64) groups of 64 (8 encodes as 0).

## Correctness (`kernels/uK.bin`: thread i writes i + u_K; each run first in `agx_run`, same result)

| K read | Halves preloaded | Uniform words | GPU wrong (64 threads x 2 reps) |
| --- | --- | --- | --- |
| u69 | 140 (B9's request) | 64 + 64 + 12 | 0 |
| u127 | 256 | 4 x 64 | 0 |
| u128 | 258 | 4 x 64 + 1 high (2) | 0 |
| u255 | 512 (whole file) | 4 x 64 + 4 high x 64 | 0 |

So: **the limit is the 512-half (1 KiB) uniform file**; a 140-half preload is fine; and **one Uniform word can
carry 64 halves** (B2b: agx_runtime's 32-half split works but uses twice the words needed).

## Cost (`gpu/cost_N_round.txt`, `u4.bin`, 65,536 threads, 64 reps, first 4 dropped, AC power)

| Halves | 20 | 64 | 140 | 256 | 512 |
| --- | --- | --- | --- | --- | --- |
| round 1 min / median fw ns | 11167 / 11459 | 13209 / 15833 | 11375 / 11792 | 11292 / 11666 | 11500 / 11834 |
| round 2 min / median fw ns | 11459 / 13292 | 11333 / 13166 | 8375 / 9625 | 8834 / 10166 | 9041 / 10041 |

No trend with size; differences are within the run-to-run clock-state variation seen elsewhere (S1).

## Open

- Reading a parameter buffer from memory instead (for CUDA's 4 KiB parameter space beyond 1 KiB) was not timed.
- B2c (whether the "no shared memory" encoding, which Mesa also uses: bytes 65536 with uses_shared_memory = 0,
  limits occupancy) is left for the occupancy probes (B5 / B26).
