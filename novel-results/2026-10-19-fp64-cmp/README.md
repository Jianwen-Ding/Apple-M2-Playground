# fp64 compares are bit-exact: all 18 setp / min / max / .u / set forms, 5,312 lanes x 3 runs

Status: confirmed on one device (driver-reported M2 Max G14C B1; user confirms board is a MacBook M2 Max),
direct DRM, compute stage, AC power. Straight-line branch-free programs built only from recorded-safe
integer ops (`softfp64.py` builders `fcmp_*`, same DSL as the fp64 add/mul/fma). Every program ran in the
Rust simulator against the IEEE host model before hardware; 18 ops x 3 runs, 0 faults (hang budget untouched).

## Result

| Ops | Instructions | Registers | Hardware check |
|---|---|---|---|
| `setp.{eq,lt,gt,le,ge}.f64` (NaN -> false) | 55-61 | r0-r20 | 5,312 lanes x 3, **0 differ** |
| `min/max.f64` (NaN loses, -0/+0 exact) | 49 | r0-r21 | 5,312 lanes x 3, **0 differ** |
| `.neu/.equ/.ltu/.leu/.gtu/.geu/.num/.nan` | 22-59 | r0-r20 | 5,312 lanes x 3, **0 differ** |
| `set.{lt,gt,eq}.f64` (float 1.0/0.0 result) | 55-57 | r0-r20 | 5,312 lanes x 3, **0 differ** |

Operands: all 48 x 48 EDGE pairs (subnormals, signed zeros, inf, NaN, 2^52 neighbours) plus 2,000
random doubles (30% raw bit patterns) and near-cancelling pairs per op. A NaN result matches any NaN;
`min`/`max` with two NaNs keep the first operand's bits.

## How it works

Per operand, a monotonic u64 key: sign ? ~bits : bits ^ 0x8000000000000000, with +-0 both mapped
to 0x8000000000000000 for `setp` (raw key kept for `min`/`max`, so -0 < +0). NaN = exp-max with
nonzero mantissa. Relations are unsigned key compares; `.u` variants force true on NaN; `num`/`nan`
return the inverted/combined mask; `set` selects 0x3f800000/0. All branch-free, 20-61 instructions.

## For PTX / ZLUDA

- `setp.*.f64`, `set.*.f64`, `min/max.f64` (default, non-`.ftz`) lower to these sequences today.
  `.ftz` forms compare the high word only (subnormals read as zero, like fp32 — not run, follows
  from the fp32 finding).
- Still open in fp64: `div`/`sqrt` (Newton iteration not written), `cvt` f64<->f32/int, other
  rounding modes, transcendentals, fix-up cost.

## Harness note (also in failed-approaches)

- The DSL has its own Python interpreter (`Prog.run`): run new builders through it on tricky
  pairs *before* the simulator/hardware. It caught an inverted NaN-gate select here (min/max
  always took b) that the later gates would also have caught, but earlier is cheaper.

## Reproduce

`scripts/run_drm_softfp64.py hardware --op c_<name> --random 2000 --repeats 3` (18 ops),
`make verify-fcmp64` (offline: retained records, fresh DSL-interpreter checks, `FCMP_OPS` list;
needs `agx_run` built for the simulator replay, which the hardware runs already passed).
Records: [results/2026-10-19-fp64-cmp](../../results/2026-10-19-fp64-cmp).
