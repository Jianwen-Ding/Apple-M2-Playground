# `shfl.sync` has an exact AGX lowering for every mode, clamp and segment mask; AGX shuffles are quad-granular

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. Straight-line programs, no
loops, only `simd_shuffle*` forms already recorded safe and integer ALU. Each program was run in the Rust simulator first. 0 faults.

**Sparse-mask correction (2026-10-20):** the generic sequence below was tested
with all 32 lanes active. Under divergence its index registers must also have
compatible low bits in inactive lanes. Initialize r19..r22 to 0..3 before
divergence; merely computing the four indices in active lanes is insufficient.
The [follow-up](../2026-10-20-shfl-mask/README.md) records both the failure and
the fix, plus paired b32 lowerings of arbitrary 64-bit payloads.

## Why this needs care: the index is quad-granular

`simd_shuffle` takes the **low two bits of the source lane from the OR over the source quad's index operands**, not from the reading lane
(this is how the simulator already models it and why its coverage cases pass). A per-lane index is therefore exact only when its low
two bits are the same for all four lanes of the quad it addresses. Measured negative controls (one `simd_shuffle` with a per-lane
index, 240 SIMD groups each):

* naive `shfl.idx` is **wrong on exactly the 160 groups** whose index low bits vary inside a quad (per-lane random, full-width,
  lane-permutation and ramp indices) and right on the 80 warp-uniform ones;
* naive `shfl.up` / `.down` / `.bfly` built as `index = lane +- b` is **wrong on all 240 groups, uniform b included**, because
  `lane + b` always varies the low bits. These modes must use the native `simd_shuffle_up` / `_down` / `_xor` instead.

## Lowering (exact in all tests)

PTX reference used (`shfl.sync`, membermask = all lanes): `lane = laneid; bval = b[4:0]; cval = c[4:0]; segmask = c[12:8];
maxLane = (lane & segmask) | (cval & ~segmask); minLane = lane & segmask;` up: `j = lane - bval, p = j >= maxLane`; down: `j = lane + bval,
p = j <= maxLane`; bfly: `j = lane ^ bval, p = j <= maxLane`; idx: `j = minLane | (bval & ~segmask), p = j <= maxLane`; `d = p ? a[j] : a`
(the lane's own value). (This is the PTX ISA text as I recall it; the `c` encoding agrees with ZLUDA's source: clamp 31 for idx / bfly /
down, 0 for up, segment mask 32 - width. The reference lives in `ptx_shfl()`.)

| Case | AGX sequence | Instructions | Tested |
| --- | --- | --- | --- |
| any mode, **constant b**, default clamp (width 32) | `simd_shuffle_up` / `_down` / `_xor` / `simd_shuffle rD, rA, imm(b & 31)` | **1** | every b = 0..63, all 4 modes: exact |
| any mode, per-lane or non-default `b` / `c` (width < 32, any segment mask) | compute `j`, `p` with integer ops; `ix = p ? j : lane`; four `simd_shuffle` with the low bits forced to 0..3 on `(ix & 28) \| k`; select on `ix & 3` | 21 (up / down / bfly), 22 (idx) | 48 configs: widths 32, 16, 8, 4, 2, 1 and 6 random 13-bit `c` per mode; indices uniform / per-lane small / full 32-bit / permutation / edge values / ramp: exact |
| the predicate output `p` | the `icmpsel` in the sequence | included | exact |

* Out-of-range lanes keep their own value on AGX for `index >= 32`, but PTX masks `b` to 5 bits (b = 33 behaves like 1), so `b & 31`
  must be applied; the generic sequence does, and the fast path folds it at compile time.
* 7,680 lanes (240 SIMD groups) per program on hardware, replayed identically in the simulator.

Not established: `membermask` other than all ones (PTX requires every named lane to execute the instruction; a source lane that is
inactive was not measured), shuffles of 16/64-bit values (two shuffles for 64-bit), `.b32` vs the `f32` forms (bit-identical
moves), and the cost of the generic sequence versus the single instruction (measured 2026-10-20: [~18x](../2026-10-20-shfl-cost/README.md)).

## Reproduce

`scripts/run_drm_shfl.py offline|hardware`; `make verify-shfl` (offline: 10 checks of the retained records plus a simulator replay of
all 308 programs; `--no-sim` skips the replay). Records: [results/2026-10-18-shfl](../../results/2026-10-18-shfl).
