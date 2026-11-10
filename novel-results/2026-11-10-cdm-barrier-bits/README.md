# CDM barrier bits between dispatches of one compute command: G14C — 2026-11-10

M2 Max (G14C), Asahi 6.19.14, ZLUDA's direct DRM path (one compute command whose control stream holds several
dispatches, each followed by a CDM barrier word `3 << 29 | bits`). Mesa's genxml names bit 3 `USC cache inval` and
the others `Unk N`; ZLUDA used Mesa's blit-safe set, bits 0-19 (`0xfffff`).

## Method

- `lb2.c`: a CUDA graph of 64 launches of a 32-thread kernel, the graph launched 100x back to back (the GPU's clock
  ramped), best of 5 / 6400 dispatches. Kernels: `k0` (empty), `k1`/`k2` (400 xor-shift-multiply steps, ~7 KB of
  straight-line code each). Modes: `tiny` (k0 x64), `same` (k1 x64), `alt` (k1, k2 alternating).
- `lbc.c`: correctness: 64 ping-pong dispatches `out[t] = in[(t + 28693) % N] + 1` over 152 (or 4) workgroups of 256,
  the graph launched 50-200x; every value must end at 64 x launches. Catches dispatches that overlap or read stale data.
- `lb.c`: per-command and per-dispatch cost (graph of 1/8/64 launches).
- The barrier word was set with ZLUDA's `ZLUDA_AGX_ORDER_BARRIER_BITS=HEX` (commit 5fdb973c).

## Results

1. **A command costs ~16 us, a dispatch in it ~2.6-3 us** (empty kernel, 1 vs 64 dispatches: 18.4 / 193 us). Barrier
   or not (disjoint buffers) makes no measurable difference for an empty kernel.
2. **Bit 11 invalidates the instruction cache** (with any of the low bits set): `same` costs 16.3 us per dispatch
   with `0xfffff`, 7.0 without bit 11 (`0xff7ff`), 6.9 with `0x3ff`. Adding single bits to `0x3ff`: only bit 11 brings
   back 16 us (all others 6.8-7.4). Bit 3 (`USC cache inval`) alone does not (`0xffff7`: 15.6). `alt` stays ~16 us
   with every mask: two 7 KB kernels do not fit the 12 KB cache together. An empty kernel: ~3 us with any mask.
3. **Ordering needs bit 8 with bit 5 or 6** (Mesa's base set `0x160`): `0x160`, `0x1e0`, `0xff`, `0x17f`, `0x1ff`,
   `0x3ff`, `0xff7ff` exact; `0x7f`, `0x3f`, `0xfff00` wrong in every value (the dispatches overlap: `0x7f`/`0x3f`
   cost 2.3 us for the 7 KB kernel, i.e. they run concurrently).
4. The data written by one dispatch and read on another core by the next is visible with all the exact masks above.

## Use

ZLUDA (5fdb973c) puts `0xfffff & ~(1 << 11)` between the dispatches of a command and keeps the full barrier at the
command's end and after newly loaded code. llama.cpp completions, Rodinia hotspot/pathfinder/srad_v2 outputs are
unchanged; llama.cpp token generation is not faster (its ~500 dispatches per token alternate kernels whose code
exceeds the cache together), srad_v2 ~5%.

Simulator: a dispatch that repeats the previous dispatch's kernel within a command can start with a warm i-cache
(not modelled; the captures time single kernels back to back in separate commands).
