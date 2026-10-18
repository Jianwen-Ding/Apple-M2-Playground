# Texture and image semantics through Mesa GLES: encodings and exact conversion rules

Status: confirmed on one device (driver-reported M2 Max G14C B1). safe-05 steps 1-2, partly. Mesa builds every texture, sampler and image
state word; no state was hand-encoded or edited and the driver never rejected a bound texture. 10 GLSL ES 3.2 compute shaders, outputs recorded as raw
words, AGX listings captured from Mesa's shader cache. 0 faults, no hang-budget use.

## Encodings Mesa emits (from the captured listings)

* `texelFetch` -> `texture_load` (2D, `auto_lod`, 0b1100 mode word); read-only `imageLoad` -> `texture_load` with mode 0b1101 and `lod_min`.
* `textureLod` (nearest or linear, any wrap mode) -> `texture_sample ..., ts0, ss1, tex_2d, ..., lod_min`: filtering and address mode live in the
  **sampler state** (`ss1`), not in the instruction. Sampler 0 (`ss0`) is used by the loads.
* `imageStore` -> `image_write` (`ts1`, `rte`) for r32f; the epilogue-style `image_write_block` (`ts2`, `rte`, `u8norm` / `i32` / `i16`) is the
  fixed output write seen in every GLES compute shader.
* Listings: `results/2026-10-18-gles-texture/listings/`, shaders next to them.

## Measured semantics (all exact, no exceptions)

| Question | Result | Cases |
|---|---|---|
| unorm8 -> float | `float32(k/255)` | 256 / 256 |
| snorm8 -> float | `max(k/127, -1)`; -128 and -127 both give -1 | 256 / 256 |
| sRGB8 -> float | `float32(round(srgb(k) * 4095) / 4095)`: a **12-bit** result, not the float formula (float32 of the formula matches only 2 of 256) | 256 / 256 |
| half float fetch | exact for every non-NaN pattern incl. denormals and -0; NaNs stay NaN | 65,536 |
| bilinear weights | result = `float32(floor(exact * 16 + 0.5) / 4080)`: the filtered unorm value is rounded half-up to 1/16 of an 8-bit step (12 bits); neither floor nor ties-to-even fits | 3,840 (256 sub-texel positions x 15 cells) |
| address modes (nearest, x -20..35) | clamp-to-edge, repeat and mirrored-repeat all exact | 3 x 56 |
| rgba8 `imageLoad` | same unorm conversion as sampling a texel | 512 |
| r32f store then load | bit exact | 1,024 |

The 12-bit grid is the common cause of the sRGB table and the bilinear rounding: filtered unorm results are held with 4 fractional bits beyond 8.
The 10 sub-texel bits found in the earlier `texfilter` work are consistent: the weights here resolved all 256 positions per texel (8 bits).

## Not done

* Border-colour and out-of-range integer coordinates, 1D/3D/array/cube targets, LOD and gradient forms, snorm16 / unorm16 and 32-bit integer formats,
  sRGB filtering, `tld4` equivalents.
* Simulator implementation (`texture_load` / `texture_sample` / `image_write`) and the CUDA mapping table (steps 3-4). The rules above are the
  functional model to implement.
* Textures are 2D only; the harness (`tests/gles_compute.c`, `GLES_TEX_*`) covers formats r8, rgba8, r8snorm, rgba8snorm, rgba8srgb, r16f, r32f,
  rgba32f, r8ui and r32ui (only the first seven were run).

## Reproduce

`python3 scripts/run_gles_texture.py` (writes to `/scratch/apple-m2-playground/gles-texture`); `make verify-gles-texture` (offline, 10 checks).
