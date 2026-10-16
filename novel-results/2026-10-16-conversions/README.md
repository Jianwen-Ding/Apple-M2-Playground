# `convert`: exact semantics over 1.37 billion inputs, and its PTX `cvt` mapping

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power. Simulator task
safe-01 part 1.

## Claim and scope

**Test:**
- 80 forms of AGX `convert`: modes 0, 1 and 4-11 (the `safe` ones; modes 2, 3 and 12+ are on the do-not-run list),
  round field 0 (float → int) and 1 (int → float), 16- and 32-bit destinations and sources.
- 1,372,198,046 inputs: every fp32 in each binade around the integer range, edge-dense elsewhere (both ends, random,
  exact .5 ties with both neighbours), every fp16, every 16-bit integer pattern, and 32-bit integers dense around
  fp32 / fp16 rounding ties. Each chunk ran twice.
- Each kernel first passed the simulator's `agx_run` against the model on ~12k sampled inputs.
- The simulator's model matches **every** word (`AGX-Performance-Simulator`: `make verify-conversions`,
  `results/2026-10-16-conversions`).

**The mode field** (`mode = width << 2 | rte << 1 | signed`):

| bits | meaning |
|---|---|
| 0 | signed (1) / unsigned (0) integer |
| 1 | round to nearest even (1) / toward zero (0) |
| 3:2 | integer width: 0 = 8, 1 = 16, 2 = 32 bits |

**Float → integer (round field 0):**
- fp32 sources: **denormals read as ±0**. fp16 sources (`r6l`) are full IEEE.
- Rounding: nearest even (2.5 → 2, 3.5 → 4) or toward zero, per mode.
- **Saturates** to the integer range; +inf → max and −inf → min. **NaN → 0**, and −0.0 → 0.
- The result is masked to the width and **zero-extended**: 8-bit signed −1.0 → `0xff`, 16-bit → `0xffff`.

**Integer → float (round field 1):**
- The source is the low `width` bits of the register, sign-extended if signed. Upper bits are ignored.
- fp32 destination: nearest even or toward zero, per mode. Unsigned 0xffffffff → 2^32.
- fp16 destination (`r14l`): nearest even overflows to ±inf at ≥ 65,520. **Toward zero gives 65,504 up to 65,535
  but ±inf from 65,536 on.** IEEE round-toward-zero would give 65,504.

## PTX `cvt` mapping (PTX ISA 9.7.9.21)

| PTX | AGX | Note |
|---|---|---|
| `cvt.rni.s32.f32` / `.rzi` | `convert` mode 11 / 9 | exact, incl. saturation and NaN → 0 |
| `cvt.rni.u32.f32` / `.rzi` | mode 10 / 8 | exact |
| `cvt.rmi` / `.rpi` `.{s,u}32.f32` | `floor` / `ceil`, then mode 9 / 8 | 2 instructions. Non-`.ftz`: PTX gives ceil(+denormal) = 1 and floor(−denormal) = −1, but the DAZ path gives 0, so an input-exponent test is needed |
| `cvt.*.{s,u}16.f32`, `cvt.*.{s,u}8.f32` | modes 4-7 / 0-1 | saturates like PTX. **Signed results are zero-extended**: add a sign extension (`bfeil` / shift pair) when the destination register is wider than the type |
| `cvt.*.{s,u}{8,16,32}.f16` | same modes with a 16-bit source | full IEEE fp16 input, so no denormal issue |
| `cvt.rn.f32.{s,u}{8,16,32}` / `.rz` | round field 1, modes 1-11 | exact |
| `cvt.rm` / `.rp` `.f32.{s,u}32` | no direct mode | e.g. `.rz` convert, then step one ulp away from zero when the conversion was inexact and the sign matches (inexact test: convert back with `.rzi` and compare). About 4-5 instructions |
| `cvt.rn.f16.{s,u}32` | mode 11 / 10 → 16-bit destination | exact |
| `cvt.rz.f16.{s,u}32` | mode 9 / 8 → 16-bit destination | clamp the source to ±65,504 first (|x| ≥ 65,536 would give ±inf) |
| `cvt.*.{s,u}64` ↔ float | none (no 64-bit width) | software sequence |
| `cvt.f32.f16` | `fadd32 rD, rS16, -0.0` | exact for all 65,536 inputs incl. fp16 denormals; NaN → `0x7fc00000` (payload lost) |
| `cvt.rn.f16.f32` | `fadd32 rD16, rS, -0.0` | IEEE round to nearest even over 285 M inputs, incl. fp16 denormal results; NaN → `0x7e00` |
| `cvt.rni` / `rzi` `.f32.f32` | `rint` / `trunc` | exact (a denormal rounds to ±0 either way); NaN canonical |
| `cvt.rmi` / `rpi` `.f32.f32` | `floor` / `ceil` + fix-up | non-`.ftz`: −denormal → −1.0 and +denormal → +1.0, via `iadd` + `icmpsel` (below; verified on the GPU) |

## fp32 boundary behaviour and the PTX non-`.ftz` fix-ups (safe-01 part 3)

**Data:** sweeps over the edge set, edge-dense binades and every fp16. The simulator matches every compared word
(`AGX-Performance-Simulator`: `make verify-float-edges`, 25 checks, `results/2026-10-16-float-edges`).
- **`floor` / `ceil` / `trunc` / `rint`:** IEEE except that **denormal inputs read as signed zero**
  (ceil(+denormal) = +0, floor(−denormal) = −0), and NaN → `0x7fc00000`.
- **`fcmpsel eq/lt/gt/lte/gte`:** IEEE compares with denormals read as zero.
- **`fcmpsel ltn` / `gtn`:** a NaN in `a` selects `b` and a NaN in `b` selects `a`. So `fcmpsel ltn, d, a, b, a, b`
  is **IEEE minNum** (PTX `min.f32`) and `gtn` is maxNum, in one instruction (denormals compared as zero).
- **`fadd32` to / from a 16-bit register:** exact IEEE f32 ↔ f16 conversion, as in the table above.

**Fix-up for `ceil` / `floor` (and `cvt.rpi` / `cvt.rmi`) without `.ftz`**, verified on the GPU on 57,439 inputs
(the edge set, every power-of-two boundary denormal, 2 × 16,384 random denormals, edge-dense normal binades): the
hardware equals the IEEE oracle (`scripts/verify_rounding_fixup.py`).
```
ceil  r14, r6                         floor r14, r6
mov   r21, 0xffffffff                 mov   r21, 0x7fffffff
iadd  r20, r6, r21                    iadd  r20, r6, r21
mov   r21, 0x007fffff ; mov r22, 1.0  mov   r21, 0x007fffff ; mov r22, -1.0
icmpsel ult, r14, r20, r21, r22, r14  icmpsel ult, r14, r20, r21, r22, r14
```

**PTX default (non-`.ftz`) `.f32` operations:**

| PTX | Status on AGX |
|---|---|
| `add` / `sub` / `mul` / `fma` `.rn.f32` | **not exact** for denormal operands or results (DAZ, and flush before rounding; `2026-10-11-float-semantics`). The `.ftz` forms map directly, except at the min-normal rounding boundary. Exact non-`.ftz` needs a software path (scaling) |
| `cvt.rmi` / `rpi`, `cvt.rmi.f32.f32` etc. | `floor` / `ceil` + the fix-up above (3 ALU + 2 moves) |
| `cvt.rni` / `rzi` (int or float result) | direct |
| `setp.*.f32`, `selp` on compares | DAZ compares. Non-`.ftz` needs a fix-up when an operand is denormal (e.g. compare as sign-magnitude integers). **Not yet verified** |
| `min` / `max.f32` | `fcmpsel ltn` / `gtn`. NaN handling matches; a denormal compares equal to 0, so min(0, +denormal) returns the denormal. **Not yet verified as a PTX fix-up** |
| `cvt.f32.f16` / `cvt.rn.f16.f32` | direct, exact (NaN payloads canonicalised) |

## Reproducer and evidence

- `AGX-Performance-Simulator`: `scripts/record_convert.py` (GPU, resumable, agx_run-gated) and
  `make verify-conversions` (offline).
- `results/2026-10-16-conversions/hw_samples.json.gz`: ~12k samples per form, plus the SHA-256 of each full result
  array (the full arrays live in `/scratch/agxsim-data/convert`).

## Relationship to existing knowledge

applegpu lists `convert` with its `src` / `round` / `mode` fields, but its semantics are TODO. Mesa emits specific
modes without documenting saturation, NaN or the fp16 round-toward-zero overflow. The mode bit meanings, the
zero-extension of narrow results and the overflow quirk were measured here.
