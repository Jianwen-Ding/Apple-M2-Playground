# A cold jump target's fetch cost depends on the jump: 294 ns (next line) to ~400 ns (8+ lines); short jumps stream

Status: one device (M2 Max G14C), 2026-11-25, idle GPU on AC power, fresh boot. Our own hand-assembled kernels only
(`iadd`, `jmp_exec_any`, `wait`, `stop`: forms the coverage suite records as safe), run with agx_run_hw back to back
(200 commands, firmware timestamps). Nothing was disassembled or decompiled. One run of the 80 faulted (see Caveats).

Follow-up of [uncached jump fetch](../2026-11-07-uncached-jump-fetch/README.md), whose "jump to the next line (324 ns)
is slower than a random target (235 ns)" was unexplained.

## Set-up

One SIMD group runs N one-line blocks (7 `iadd` + `jmp_exec_any` + `wait 0` filler = 64 bytes). The instruction cache
does not survive the command boundary, so every line is a first fetch. The cost is the slope between two N, in ns per
block (about 30 ns of it is execution). Lines between blocks that never run are `stop` filler. Using `wait 0` or `iadd`
filler instead adds only 5%, so the filler's content barely matters.

## Results

The per-block cost does not depend on the code size: 16 KiB, 64 KiB and 512 KiB give the same value to within 1%.
So what is measured is the jump, not a cache capacity.

**First touch, single pass** (each block jumps d lines, and nothing near the target was fetched before):

| d (lines) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 12-48 | 64 | 96-512 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| forward | 324 | 327 | 342 | 368 | 376 | 374 | 399 | 430 | 420-428 | 367 | 398-408 |
| backward | 322 | 323 | | 358 | | | | 425 | | 367 | |

- Random gaps give the same values as constant ones (8-64 lines: 397; 64-512: 403; descending 403-410).
- There is a dip at 4 KiB and 8 KiB strides (64 and 128 lines: 364-367), not explained.

**A short forward jump keeps the sequential stream.** Two passes: lines iG, then lines iG+o.

| Stride G | Pass 2 cost (ns) |
|---|---|
| 2 | 187 |
| 4 | ~130, for every o |
| 8, 16, 32, 64 | as cold as pass 1 (415-430) |

So the lines a jump of 4 or fewer lines passes over are fetched along with it. A jump of 8 lines or more fetches nothing
in between. The interleaved-chain orders (fwdK) agree: stride 2/3/4 cost 257/228/216 per block.

**Random order reuses 512-byte blocks.** Random order over every line costs 238, over every 2nd line 267, and over every
4th, 8th, 16th, 64th or 256th line 405-413. A random target is cheap only when other lines of its block were fetched
before. A block that had just one line fetched gives nothing: lines 8i then 8i+1, 2, 4 or 7, at reuse windows of 1 to
128 blocks, cost 412-425. This is the model's rule: "2 or more lines fetched in the target's 512 B block → ~150 ns".

Model fit (AGX-Performance-Simulator `cost::JumpFetch`): over the 79 shapes, mean |error| is 6.0% (median 3.2%). The
earlier flat 300 ns gave 18.2% (median 19.6%). Not fitted:

- interleaved chains of stride 16-64 lines (hw 343-348, rule -31%);
- backward jumps when the lines above were fetched (back d=-1: hw 323, rule 216);
- the 4 / 8 KiB stride dip.

## Implication

- **Compiler:** in large code, a taken branch to a cold line costs up to ~400 ns: about 5.7x a streamed line (70 ns).
  If-skips over 1-4 lines cost about the same as running through. Laying cold paths far away costs ~400 ns when they
  are taken, and nothing when they are not.
- **Simulator:** charge jumped-to cold lines by distance, not with one flat value.

## Caveats

- One kind (win32_8_1, N=256) failed with fence status -EFAULT, i.e. a GPU fault. Its neighbours, with the same
  instruction forms and padding, ran fine. The GPU recovered. The kind was not retried, and dmesg was not readable.
  This is the same symptom class as the two unexplained 2026-11-06 faults of the first probe.
  - Suspect: instruction prefetch reading past the code object's 16 KiB stop pad.
  - Recorded in AGX-Performance-Simulator `coverage/faults.json`.
  - Before rerunning, use a larger pad and read the fault address.
- Only one SIMD group was measured. How several groups share these fetches was not measured.

## Reproduce

AGX-Performance-Simulator `scripts/probe_jump_distance.py [hw|sim]` with `KINDS=...`, `N1`, `N2` and `FILL` set, on an
idle GPU, after `gpu_safety.py status`. The data is in [hardware.jsonl](../../results/2026-11-25-jump-fetch-distance/hardware.jsonl) (also in the simulator's `results/2026-11-25-jump-fetch/`), and
`make verify-jump-fetch` checks the model offline.
