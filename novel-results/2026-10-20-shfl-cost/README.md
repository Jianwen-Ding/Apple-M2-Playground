# `shfl.sync` cost: native shuffle ≈ 2× iadd, generic lowering ≈ 18× native; warp-uniform runtime offsets need only `and` + native op

Status: one device (driver-reported M2 Max G14C B1), direct DRM, straight-line programs using already-recorded safe forms,
simulator-gated, and every hardware output compared exactly against the simulator. 0 faults, hang budget unused.
This closes the cost item left open by the [2026-10-18 shfl finding](../2026-10-18-shfl/README.md).

## Cost (dependent chains)

Each lane runs K dependent shuffles: the result is the next iteration's source. The generic sequence recomputes its index
math every iteration, as a compiler would. 131,072 lanes, firmware time, median of 5-7 runs, cost = slope against K.

| Lowering | Instructions per step | ns per step (131,072 lanes) | Relative |
|---|---|---|---|
| dependent `iadd` (reference) | 1 | 77 | 0.5 |
| `simd_shuffle_xor r, r, 1` | 1 | 166 | 1 |
| `simd_shuffle_up r, r, 1` | 1 | 160 | 1 |
| `simd_shuffle r, r, r9l` (uniform register index) | 1 | 155 | 1 |
| generic idx / up / bfly (2026-10-18 sequence) | 22 / 21 / 21 | 2975 / 2933 / 2880 | ≈ 18 |

Native slopes come from K = 1024 → 2048; at K ≤ 128 they are below the 25-35 µs launch noise. Generic slopes come from
K = 1 → 128, and are linear within 10% of K = 1 → 64.

## Register-amount native forms

The native ops accept a register amount (`simd_shuffle_down r28, r8, r9l`). Tested against PTX `shfl.sync` with the default clamp,
240 groups in six data kinds (as in the 2026-10-18 run):

| Variant | Warp-uniform b (0..40 and edges 0..3/31/32/33/63) | Per-lane b |
|---|---|---|
| `op rD, rA, r9l` raw | wrong whenever b ≥ 32: the register form does **not** apply PTX's 5-bit mask | wrong |
| `and r9, r9, 31; op rD, rA, r9l` | **exact in all four modes** (up / down / bfly / idx, 80/80 groups each) | wrong (40/40 per kind) |

## Compiler implications (ZLUDA)

1. Constant b with the default clamp: one native instruction (2026-10-18).
2. **Warp-uniform runtime b with the default clamp** (for example a non-unrolled `for (o = 16; o; o >>= 1) v += __shfl_down_sync(~0, v, o)`):
   `and b, 31` + native op, 2 instructions, about 18× cheaper than the generic sequence. This needs a uniformity analysis to prove b is warp-uniform.
3. Per-lane b, non-default c or a segmented width: the generic sequence. Its cost (~18 native shuffles) argues for specializing every
   case that can be proved uniform. A width < 32 with constant b could likely be lowered more cheaply, but that was not measured.

## Not established

- Issue-rate versus latency split: the chains are dependent, so these numbers mix throughput and latency at full occupancy.
- `simd_shuffle_down` and `idx` with immediate amounts were not timed separately; the costs of `up`/`xor`/register `idx` were equal.
- Not yet wired into `cost.rs`.

## Reproduce

`python3 -B scripts/run_drm_shfl_cost.py offline` (simulator gate), then `hardware --result ...` (default kinds, K 1/64/128) and
`hardware --ks 64,1024,2048 --repeats 7 --kinds iadd,xor1,up1,idxreg`. Next, `python3 -B scripts/run_drm_shfl_regamt.py offline|hardware`.
Offline check: `make verify-shfl-cost` (8 checks against [results/2026-10-20-shfl-cost](../../results/2026-10-20-shfl-cost)).
