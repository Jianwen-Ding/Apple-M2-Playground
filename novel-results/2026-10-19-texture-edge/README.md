# Texture edge cases: OOB texelFetch returns 0, gather footprint rule, sRGB bilinear is 12-bit end to end

Status: confirmed on one device (driver-reported M2 Max G14C B1; user confirms board is a MacBook M2 Max),
Mesa GLES compute. Mesa builds every texture, sampler and image state word; nothing was hand-encoded
and the driver never rejected a bound texture. 3 new GLSL ES 3.2 compute cases (17-case suite green,
guards intact), AGX listings captured from Mesa's shader cache, 0 faults.
This is safe-05 step 2 progress ([remaining-work](../docs/remaining-work.md) row 9).

## Encodings Mesa emits (from the captured listings)

- Out-of-range `texelFetch` uses the identical `texture_load` encoding as in-range
  (`0, 0b1100, 0b0, none, x, 0b00, r4, None, ts0, ss0, tex_2d, r2_r3, auto_lod, 0`): the zero
  comes from hardware execution, not a separate path.
- `textureGather` -> `texture_sample 0, 0b1100, 0b0, gather_r, xyzw, 0b00, r4_r5_r6_r7, None, ts0, ss1, tex_2d, r4_r5, auto_lod, 0` (the `tld4` equivalent form).
- Linear `textureLod` on an sRGB texture -> the same `texture_sample ... lod_min ... u10l` form
  as unorm sampling; filtering precision lives in the sampler/hardware, not the instruction.

## Measured semantics (all exact, no exceptions)

| Question | Result | Cases |
|---|---|---|
| `texelFetch` with out-of-range integer coords (x/y in -8..23 on a 16-texel axis) | every OOB lane returns **0** (no fault, no clamp); all 32 in-range lanes exact | 32 OOB + 32 in-range |
| `textureGather` 2x2 footprint and component order (axis sweeps at texel-corner uv) | footprint box per axis = **(ceil(c)-1, ceil(c))** in texels (at integer coords: the texel below/left, not the GL-spec floor,+1); components return in order **((x0,y1),(x1,y1),(x1,y0),(x0,y0))**; OOB refs clamp to the edge per texel | 64/64 lanes |
| bilinear filter of an sRGB texture (256 sub-texel positions x 15 cells, fy = 0.375) | taps decode with the 12-bit fetch rule (`round(srgb*4095)/4095`), bilinear with exact weights, **result rounded to nearest 1/4095** as float32: `float32(round(exact*4095)/4095)` | 3840/3840 |

The 12-bit grid is end to end for sRGB: decode and filter-result both live on it (consistent with
the unorm findings: filtered unorm values use 1/16-of-8bit-step rounding, i.e. the same 12 bits).

## Border colours (`CLAMP_TO_BORDER`)

`tests/gles_compute.c` now takes `GLES_TEX_WRAP=border` plus `GLES_TEX_BORDER="r,g,b,a"` (float,
for normalized/float formats) or `GLES_TEX_IBORDER` (uints, for integer formats). The instruction
is the same `texture_sample` form; the border lives in sampler state.

| Question | Result | Cases |
|---|---|---|
| float border 0.5 on r8, nearest, x in -20..35 | OOB lanes read `float32(128/255)`: the colour **quantizes to the texture format** (round-half-up 0.5*255 = 128) before sampling; 16/16 in-range exact | 40 OOB + 16 in-range |
| float border 0.0 on r8 | OOB lanes read exactly 0.0; in-range exact | 40 + 16 |
| integer border 0x12345678 on r32ui (normalized `textureLod`; `texelFetch` ignores wrap modes) | OOB lanes read exactly 0x12345678; in-range exact | 40 + 16 |
| linear blend into a 0.25 border at the left edge (x_tex in -0.5..0.5) | follows the standard 12-bit unorm rule with the **quantized** border (64): `floor(blend*16+0.5)/4080` | 256/256 |

Note the test-design trap this closed: `texelFetch` takes raw integer coordinates and ignores
the sampler wrap mode entirely, so the first integer-border attempt (via `texelFetch`) measured
the OOB-returns-0 rule instead of the border. Integer borders need a normalized lookup.

## 16-bit formats (all 65,536 values each)

`tests/gles_compute.c` now takes `r16` (`GL_R16_EXT`), `r16snorm` (`GL_R16_SNORM_EXT`) and `r16ui`
(core `GL_R16UI`); the driver accepted all three, so no extension fallback was needed.

| Question | Result | Cases |
|---|---|---|
| r16 unorm `texelFetch` | `float32(k/65535)` | 65,536/65,536 |
| r16 snorm `texelFetch` | `float32(max(s/32767, -1))`; -32768 and -32767 both give -1 | 65,536/65,536 |
| r16ui `texelFetch` | exact identity | 65,536/65,536 |

The encoding is the same `texture_load ... auto_lod, 0` form as the 8/32-bit fetches.

## Not established by this run (safe-05 remainder)

Border wrap on the remaining formats (snorm/sRGB/integer-linear), 1D/3D/array targets (needs
texture-target harness work), LOD and gradient forms with mipmaps (needs multi-level harness),
integer filtering formats, cube maps, simulator model (`texture_load` /
`texture_sample` in `func.rs`) and the CUDA mapping table (steps 3-4).

## Harness notes

- `tests/gles_compute.c` is still 2D-only (`GL_TEXTURE_2D`, one level, clamp/repeat/mirror).
  The three cases above needed no harness change (shader-side coordinates and builtins only).
- `run_gles_texture.py --only NAME` overwrites the shared `record.json`; a full run writes the
  retained 17-case record. The RNG stream is order-sensitive: the verifier replays the exact
  draw order (bilinear 256 + wrap 256 + r32ui 256 + f32 248 draws precede the new cases).

## Reproduce

`python3 scripts/run_gles_texture.py` (full 17-case suite), `make verify-texture-edge`
(offline: OOB/gather/sRGB rules against [results/2026-10-19-texture-edge](./../results/2026-10-19-texture-edge/)).
Shaders and captured AGX listings are retained next to the record.
