# Device atomics with partly colliding lanes: same-word lanes serialise, distinct words of a 32-byte sector combine, sectors of a 128-byte bank follow one another; float adds cost ~3x int adds; Blender Cycles' film accumulation spends ~40% of shade_background in them

Status: confirmed on one device (M2 Max G14C), 2026-11-12, own probe kernel
(AGX-Performance-Simulator `scripts/probe_atomic_lines.py`, built with agx_asm + Mesa's atomic encoding, checked in
agx_run) through agx_runtime (agx_run_hw `--back-to-back 200`), and a patched copy of a ZLUDA-compiled Blender Cycles
kernel (our clang/ZLUDA build). Nothing disassembled or decompiled.

## Probe

Each lane's word = (lane & MASK) * SPACING (PERWG=1: + workgroup id * 64 words, every workgroup its own lines), T
trips of a no-return `atomic add` (or FADD=1: float32 add = op `sub` with u5 = 3) per thread, 38 workgroups (one per
core) of G SIMD groups unless noted. Numbers: GPU-wide ns per lane-operation (time / all lane-ops).

| pattern (MASK:SPACING) | lanes per word | int add | float add |
|---|---|---|---|
| 0:1 one word | 32 | 0.861 | 2.502 |
| 1:1 2 words, one sector | 16 | 0.431 | 1.252 |
| 3:1 4 words, one sector | 8 | 0.217 | 1.044 |
| 7:1 8 words (32 B) | 4 | 0.114 | |
| 15:1 16 words (one line) | 2 | 0.114 | |
| 31:1 32 words (2 lines) | 1 | 0.108 | 0.315 |
| 7:2 8 words over 64 B | 4 | 0.217 | |
| 3:4 4 words, 16 B apart | 8 | 0.431 | |
| 3:16 4 lines | 8 | 0.406 | 2.502 |
| 1:16 2 lines | 16 | 0.810 | 4.169 |
| 31:16 32 lines | 1 | 0.082 | |
| PERWG 0:1 (own word per workgroup) | 32 | 0.106 (G=4: 0.120) | 0.415 |
| PERWG 3:1 | 8 | 0.033 (G=4: 0.028) | 0.106 |
| 1 workgroup alone, 0:1 | 32 | 1.66 (53 ns / instruction) | 2.59 |
| 8 workgroups, 0:1 | 32 | 0.865 | 4.18 |

- Int adds, all cores on one array: the time per instruction is 0.86 ns x U, where U = (in the busiest 128-byte bank)
  the sum over its 32-byte sectors of the sector's busiest word's lane count. Distinct words of a sector combine
  (3:1: 8, not 32); words in different sectors of a bank do not (3:4: 16; 7:2: 8); different 128-byte banks proceed in
  parallel (3:16: 4 lines in 2 banks: 16; 31:16: fast). Every case above fits within ~10%.
- Words private to each workgroup still share a GPU-wide atomic throughput: ~0.11 ns (int) / ~0.42 ns (float) per
  serial lane-unit GPU-wide, i.e. one core alone runs 2.4-6x faster than each of 38 cores on private words.
- Float adds: ~2.9x the int cost on one word (2.5 ns per lane-op), and lines are not parallel (3:16 = one word of 32
  lanes; 1:16 slower still). Eight workgroups on one word (one cluster) are slower per op than 38 (4.2 vs 2.5 ns).
- Blender Cycles shade_background (512^2 64 spp, 12.2 M threads): the film accumulation (`atomic sub ... 4, 3` float
  adds into the render buffer, 14-30 lanes of a SIMD group on the same pixel's word, as consecutive threads are
  samples of one pixel) costs 54.7 -> 32.7 ms when patched out (`iadd rS, rS, 0` in place of each no-return float
  atomic; all no-return atomics: 34.6 ms). intersect_closest / shade_surface each issue 2 queue-counter atomics per
  thread with all 32 lanes on one word.

## Implications

- Compiler (ZLUDA AGX backend): aggregate same-address atomics inside the SIMD group before issuing (match lanes by
  address, reduce, one lane issues). Cycles' queue counters (all lanes, one word) would go from 32 serial units to 1,
  its film accumulation (samples of one pixel per SIMD group) from ~20 to ~2-3 units per instruction: up to ~40% of
  shade_background, and the 2 counter atomics per thread of intersect_closest / shade_surface (~15 ms of 37 in
  intersect_closest by the 0.86 ns rate).
- Simulator: AGX-Performance-Simulator `AGX_ATOMIC_MODEL=1` (+ `AGX_ATOMIC_SHARE`, `AGX_ATOMIC_SHARERS`) implements
  the units, the float factor and the private-word throughput.

## Evidence

[results/2026-11-12-atomic-collisions](../../results/2026-11-12-atomic-collisions/): `atom1.txt` (int), `atom2.txt`
(float, private words), `sbnoat.txt` (Cycles shade_background with atomics patched out), job scripts.
