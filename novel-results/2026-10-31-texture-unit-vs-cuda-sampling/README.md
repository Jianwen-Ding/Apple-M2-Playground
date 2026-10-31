# Texture unit sampling vs CUDA's texture semantics

Status: confirmed on one device (driver-reported M2 Max G14C B1), through ZLUDA-AGX's CUDA driver API, compute,
by probing only: the same random textures sampled at the same 2^20 coordinates by the texture unit
(`texture_sample` with ZLUDA's hardware descriptors) and by ZLUDA's software sampler, which follows
PTX-formalization's model of CUDA sampling (9-bit fixed-point linear weights, 8 fractional bits, as the CUDA
Programming Guide's "Linear Filtering" section states).

## Claim

1. **Point sampling is bit-identical** to the model in all 22 forms tried (`point.txt`): u8, u16, s8, s16 (read as
   integers and as normalized floats), f16 and f32; 1, 2 and 4 channels; wrap, clamp, mirror and border addressing;
   normalized and unnormalized coordinates; 1D arrays, 2D arrays and pitch-linear 2D memory; coordinates far outside
   the texture included. 2^22 output values per form.
2. **Linear filtering is not** (`linear.txt`):
   - unnormalized coordinates: within about 8e-6 absolute for f32 and u16 texels, 1.2e-4 for 8-bit ones;
   - normalized coordinates: up to 0.1-0.3% of the texel range, independent of texture size (64x32 and 1024x512
     alike): the conversion of normalized coordinates to texel positions, or the weights, are not the model's;
   - f16 textures: results rounded to half precision (up to half an f16 ulp off).

Not established: the hardware's weight precision or coordinate fixed-point format (only differences against the
model were measured), mipmapped, layered, cube or 3D textures, sRGB, and other GPUs.

## Reproducer

ZLUDA (branch claude/air-route-driver): `agx_texture_check` (zluda_agx/src/bin) and
`ptx/tools/agx_texture_sweep.sh NAME [options]`, e.g.
`ZLUDA_AGX_ZOC=.../zoc AGX_TEXTURE_CHECK=.../agx_texture_check ptx/tools/agx_texture_sweep.sh f16x4-point --format f16 --point`.

## Consequence

ZLUDA-AGX uses the texture unit for point-sampled textures by default and keeps linear filtering in software
unless `ZLUDA_AGX_HARDWARE_TEXTURES=1`.
