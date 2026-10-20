# fp64 (CUDA `double`) can be emulated bit-exactly on AGX: add 213, mul 176, fma 403 instructions

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. AGX has no fp64 unit
(no instruction takes or produces a double); every program here is straight-line, branch-free code built only from
integer instructions already recorded safe: `iadd`/`isub`, `imadd` (32 x 32 -> 64), `and`/`or`/`xor`, `extr` (funnel shift),
`ffs`, `icmpsel`, `mov_imm`. Each program was run in the Rust simulator before it ran on hardware. 0 faults.

## Result: IEEE binary64, round to nearest even, all cases

| PTX | Instructions | Registers | Hardware check |
| --- | --- | --- | --- |
| `add.rn.f64` | 213 | r0-r37 | 14,304 operand pairs x 3 runs, **0 differ** |
| `mul.rn.f64` | 176 | r0-r39 | 14,304 operand pairs x 3 runs, **0 differ** |
| `fma.rn.f64` | 403 | r0-r53 | 20,000 operand triples x 3 runs, **0 differ** |

Compared bit for bit with the host's IEEE doubles (add, mul) and with an exact rational reference (fma, one rounding).
A NaN result matches any NaN; the program returns the canonical quiet NaN `0x7ff8000000000000`.

Operands: all 48 x 48 pairs (24^3 triples for fma) of edge values (+-0, subnormals from 2^-1074 up, the smallest and largest
normals, 1 +- 1 ulp, max finite, +-inf, NaN, 2^52 / 2^53 neighbours), 8,000 random operands over the whole exponent range
(30% uniformly random bit patterns), and 4,000-plus near-cancelling operands (a + b with b within 2^-60 of -a; for fma
c within 2^-110 of -(a x b)). Subnormal inputs and results, overflow to inf, underflow to zero, signed zeros (-0 only from
-0 + -0), inf - inf = NaN, 0 x inf = NaN are all included and exact. Chains of 4 and 8 dependent operations per lane (used
for the cost slope) were exact as well (an early version of the runner built the chain reference from Python ints and
reported a false mismatch; fixed and re-run).

## How it works

Branch-free throughout (selects instead of branches, so no lane-dependent control flow). Per operand: unpack with an `ffs`
count-leading-zeros so subnormals are normalised and treated like normals. **mul:** four `imadd` 32 x 32 -> 64 partial
products, carries by `icmpsel`, normalise by one bit, round from fixed 53/guard/sticky positions. **add:** order by
magnitude, align the smaller operand with `extr` and a sticky bit, add or subtract through an xor-and-carry-in, count
leading zeros, normalise with a 64-bit funnel shift. **fma:** the exact 106-bit product, a 128-bit aligned add with sticky
using variable 4-word shifts (`extr` per word, word select by `icmpsel`), 128-bit leading-zero count and normalise. All
three share one rounding step that also produces subnormals (variable right shift with a lost-bit sticky) and overflow.
`scripts/softfp64.py` holds the generator (a small DSL with a Python interpreter and a register allocator); the same program
is the thing run in the simulator and on the GPU.

## Cost

131,072 lanes, a dependent chain of K operations per lane (K = 1, 4, 8), 9 runs each, clock keeper running; slope by least
squares over the medians of K (firmware ns; the run-to-run spread is about +-15%):

| Operation | Instructions per operation | Time per operation, 131,072 lanes | Per lane | Throughput (38 cores) |
| --- | --- | --- | --- | --- |
| `mul.f64` | 162 | 5.9 us | 45 ps | ~22 G ops/s |
| `add.f64` | 197 | 7.9 us | 60 ps | ~17 G ops/s |
| `fma.f64` | 387 | 15.8 us | 121 ps | ~8 G ops/s |

* The per-operation instruction counts are slopes between K = 1 and K = 8 (each chained operation unpacks its input again).
* For scale, a long run of independent native `fmadd32` on the same harness costs about 0.5 ps per lane-instruction (noisy:
  K = 256 came out below K = 1, K = 1024 vs 256 gives 0.52 ps). So emulated double mul / add / fma are on the order of
  90 / 115 / 230 native fp32 fma in throughput cost: a CUDA double-precision kernel runs two orders of magnitude slower than
  fp32 on this GPU, fma being the most expensive form. These ratios carry the +-15% spread and the noisy baseline.

## For PTX / ZLUDA

* `add/sub/mul/fma.rn.f64` can be lowered to these sequences today and are exact on the cases above (`sub` is `add` with the sign bit of the second operand flipped and
  `neg` / `abs` / `mov.f64` are one bit operation on the high word; those three were not run separately).
* A compiler can keep doubles as (hi, lo) register pairs: the pair form `rN_rN+1` already works for 64-bit integer ops.
* Not covered here: `div.rn.f64` and `sqrt.rn.f64` (Newton iteration on this core plus a correction step, not written),
  `rcp.f64`, the other rounding modes (`.rz .rm .rp`), `cvt` between f64 and f32 / integers, `setp.f64` and `min`/`max.f64`
  (these are integer compares of the high / low words; the same key trick as the [fcmp finding](../2026-10-18-fcmp/README.md)
  gives exact results, not run here), and transcendentals.
* Code size: about 160-400 instructions per operation inline; a library call (non-inlined function) would need the `call` / `ret`
  support measured earlier ([call/ret](../2026-10-17-call-ret/README.md)), which is restricted to uniform control flow.

## Reproduce

`scripts/run_drm_softfp64.py offline|hardware --op mul|add|fma [--chain K --lanes N --keeper]`; `make verify-softfp64`
(offline: retained records, fresh random interpreter checks and the simulator replay of all three programs; needs `agx_run`
built; `--no-sim` skips the replay). Records: [results/2026-10-18-fp64](../../results/2026-10-18-fp64).

## Update 2026-10-20: directed rounding for add / mul / fma

`fadd64` / `fmul64` / `ffma64` now take `mode` (`rn` default, which is unchanged, and `rz` / `rm` / `rp`). The modes
use `round_pack_mode`, the IEEE `.rm` signed-zero rule (an exact zero sum of non-zero terms is -0, and a zero sum of
zeros is -0 unless both are +0) and per-mode overflow to inf or max finite. **All 9 PTX forms are bit-exact on hardware**:
`add` / `mul` on 14,304 lanes and `fma` on 20,000 lanes (the edge sets plus random and near-cancelling operands),
3 runs each, identical to the simulator. Directed forms cost 8-13 instructions more than `rn` (221-225 vs 213 for add,
185-189 vs 176 for mul, 411-415 vs 403 for fma). The rational reference's overflow edge (max finite < |x| < 2^1024)
was fixed along the way. `make verify-fp64-modes` (11 checks); evidence:
[results/2026-10-20-fp64-modes](../../results/2026-10-20-fp64-modes).

