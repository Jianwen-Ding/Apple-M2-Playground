# fmadd lane offset: a masked-off source lane reads 0, and the cross-half read is timing-dependent (never safe to rely on)

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. Follow-up to the
[fmadd lane-offset finding](../2026-10-11-fmadd-lane-offset/README.md). Only encodings that already ran cleanly (the 10-byte fmadd32
form with k = 1 with and without bit 68; `mov_imm`, `if_icmp` / `pop_exec`); 0 faults. The masked program was run in the Rust simulator
first (fully active case).

## 1. Write-to-read distance for the cross-half read (lane 16 reading lane 15)

`mov_imm r9, 1.0` (the write of A), N independent `mov_imm r11, 0` fillers, then `fmadd32 r5, r9, r7, r1` in the 10-byte form with k = 1,
with bit 68 (cross) or without it (control); the instruction after the fmadd is either an ALU instruction (layout A) or a `wait` (layout B).
N = 0..8, 3 repeats (both forms) plus 12 more repeats of the bit-68 form per N: 332 dispatches. Lane 16 "crossed" = it read A from lane 15.

| What follows the fmadd | Bit 68 | Crossed |
| --- | --- | --- |
| a `wait` (layout B) | with or without | **every run** (162 of 162), at every distance 0..8 |
| an ALU instruction (layout A) | no (control) | 1 of 27 runs |
| an ALU instruction | yes, N = 0 or 1 | **never** (0 of 15 at each) |
| an ALU instruction | yes, N = 2..8 | **12-15 of 15 at each distance** (N = 2: 13, 3: 12, 4: 15, 5: 14, 6: 13, 7: 13, 8: 14) |

* The cross-half read needs **at least 2 instructions between the write of A and the fmadd** (with an ALU instruction after it) and is then
  only about 80-100% reliable at every distance up to 8: it is **not deterministic** at any tested distance. The earlier advice "keep the
  source write at least 6 instructions before the read" is wrong as a guarantee (6: 13 of 15).
* With a `wait` after the fmadd lane 16 reads lane 15 even **without** bit 68 and with the A write immediately before: the "16-lane halves"
  behaviour is a property of the following code, not of the instruction.
* **For PTX:** do not use the lane offset for a 32-lane shift (`shfl.up` across the half boundary); use `simd_shuffle_up`
  ([shfl finding](../2026-10-18-shfl/README.md)). Use the lane form only where a shift within a 16-lane half with 0 fill is wanted, and
  place no `wait` right after it if lanes 0..k-1 of the second half matter.

## 2. Inactive source lanes

210 SIMD groups with 7 mask kinds (random, even, odd, low 16, high 16, all but lane 0, lanes 0-1 of each quad), A = float(lane + 1) in r9 before the
mask, `if_icmp r0l, ugt, mask, 0, 1`, the lane form with k in {1, 2, 4, 8, 15}, B = 1.0, C = 0.0, `pop_exec`; 3 repeats x 2 following
instructions (30 dispatches).

* **An active lane whose source lane is masked off reads 0** (14,572 such lane reads over all k and both variants): never the register's
  contents (0), never another value (0). Hence the model rule: D = A[lane - k] if that lane is in the same 16-lane half **and active**, else 0.
* An active lane whose source is active reads it exactly (0 wrong in 30 dispatches); masked-off lanes are never written.
* Lanes below the start of their half read 0 as before, except the known cross-half reads (lanes 16.. reading lane 15 in 7-1,878 cases per
  variant, far more often when a `wait` follows) and, only with a `wait` after, 1-15 lanes in the first half in total.
* The Rust simulator now implements this (`lane_src`: an inactive source reads 0) and reproduces the hardware counts of every deterministic class
  for the same masks.

Not established: the rule for bit 52 over more float triples (still the 31 of the original finding), bit 74 and the grouping bits with an
inactive source, 16-bit (`fmadd16`) lane forms under a mask, and the reason lanes 0..k-1 occasionally read non-zero when a `wait` follows.

## Reproduce

`CONFIRM_GPU_FAULTS=1 python3 scripts/run_drm_bitflip.py --baseline "E2=fmadd32 r5, r9, r7, r1" --only E2 --no-gaps --raw
E2:d<N>c68r<rep>=62250000803f<N x 622d00000000>3a9552e2244222001008 ...` (distance; the two records) and `scripts/run_drm_fmadd_mask.py
offline|hardware` (masks); `make verify-fmadd-followups` (offline, 11 checks; `--no-sim` skips the simulator replay). Records:
[results/2026-10-18-fmadd-followups](../../results/2026-10-18-fmadd-followups).
