# Texture targets and filter precision: 3D, arrays, cubes, buffers; 1/256 weights, fp16 LOD, 1/64 level weight

Status: confirmed on one device (driver-reported M2 Max G14C B1), Mesa GLES compute. Mesa builds every texture,
sampler and image state word; nothing was hand-encoded. 27 GLSL ES 3.2 compute cases, all guards intact,
0 faults. AGX listings captured from Mesa's shader cache. This closes most of the safe-05 remainder
([remaining-work](../../docs/remaining-work.md) row 9).

Reproduce: `python3 -B scripts/run_gles_texture_targets.py` (GPU, safe: Mesa-compiled only), then
`make verify-texture-targets` (offline, 38 checks against `results/2026-10-20-texture-targets`).
The harness (`tests/gles_compute.c`) now takes `GLES_TEX_TARGET=2d|3d|2darray|cube|buffer` and `GLES_TEX_D`.

## Correction to an earlier finding

[2026-10-19 texture-edge](../2026-10-19-texture-edge/README.md) reported the trilinear level blend as
"float32-exact, no 12-bit rounding". Every value in that test lay on the 12-bit grid already, so the test could not
tell the two rules apart. Off-grid data shows the opposite: **the full trilinear result is rounded once to the
12-bit unorm grid** (64/64 off-grid lanes; rounding the level-0 bilinear separately matches only 56/64), and
**the level weight is quantized to 1/64**.

## Filter arithmetic (all formats)

| Question | Result | Cases |
|---|---|---|
| Spatial filter weight, x axis (r32f, single 0→1 edge, so output = weight) | `w = floor(frac*256 + 0.5) / 256`: 257 values 0..256/256, first step at frac = 8/4096 | 4096/4096 + 64/64 |
| Same in the z axis of a 3D texture | identical rule | 1024/1024 |
| Explicit-LOD level weight (r32f, L0 = 0, L1 = 1) | `fr = floor(fp16(lod) * 64) / 64`. The fp16 step is Mesa's: the `lod_min` operand is a 16-bit register written by `fmul32 r0h, ...`. The 1/64 floor is the hardware's | 4096/4096 |
| 2D bilinear r8 at random (non-dyadic) points | `floor(exact(w_q) * 16 + 0.5) / 4080` with quantized weights | 1024/1024 |
| 2D trilinear r8 off the grid | one rounding after the full blend: `q12(L0_bilinear*(1-fr) + L1*fr)` | 64/64 |
| 3D trilinear r8 (8 taps) | axis sweeps 192/192 exact. Random points 443/448; exact weights would give only 245/448. All 5 misses are within 0.02 of a 1/16-step tie, so the 3D accumulation has a small extra error not yet modelled | 448 |
| r16f bilinear | result rounded to **fp16**: 3813/3840 equal `fp16(exact)`, the rest within 1 fp16 ulp | 3840 |
| r32f bilinear (linear filtering of r32f is accepted) | 3835/3840 equal `fp32(exact)`, the rest within 1 ulp | 3840 |

CUDA relevance: AGX's weight resolution matches CUDA's documented 9-bit (1.8 fixed-point) filter weights, so
`tex2D` linear filtering differs from NVIDIA mainly in the unorm8 output grid (1/4080 steps) and the fp16 rounding
of half-float results. A ZLUDA lowering can use the hardware filter. A bit-exact emulator should take the weight
rule above. Note that `tex2DLod` LOD fractions finer than 1/64 are lost.

## Targets (encodings Mesa emits)

| Target | Instruction form | Measured |
|---|---|---|
| 3D (`tex3D`) | `texture_load ... tex_3d, r8_r9_r10, auto_lod` / `texture_sample ... tex_3d, ...` (three 32-bit coords) | texelFetch 512/512 exact (x fastest, then y, z). OOB on any axis returns 0 (96/96). Repeat/mirror/clamp in R 32/32 each. Mip depth halves per level, trilinear 12/12 |
| 2D array (`tex2DLayered`) | `texture_sample ... u0_u1, r3, ss1, tex_2d_array, r8l_r8h_r9l_r9h_r10l` (x, y 32-bit, layer as a 16-bit integer) | texelFetch 384/384 exact. OOB layers (-2, -1, 6..9) return 0. Linear filtering never blends layers (256/256) |
| 2D array, float layer coordinate | Mesa lowers it in the shader: `rint` → clamp ≥ 0 → `f_to_u32` → `icmpsel` clamp to `d-1` | layer = `clamp(roundEven(l), 0, d-1)`, so ties go to even (0.5→0, 2.5→2, 4.5→4), 161/161. GL specifies `floor(l+0.5)`. CUDA passes integer layers, so this tie case does not arise |
| Cube (`texCubemap`) | `texture_sample 0, 0b1100, 0b1, ... tex_cube, r4_r5_r6` (raw direction; the third operand bit is set) | face selection and s/t mapping done in **hardware**, matching the GL major-axis table with ties x > y > z: 214/214 including 16 tie directions |
| Buffer (`tex1Dfetch`) | lowered to **`texture_load ... tex_2d`** on a 2D view: `x = i & u14`, `y = i >> 14` (`bfeil ..., 14`), so the view is 16384 texels wide; the index is first bounds-checked with `icmpsel ult i, size ? i : sentinel`; a uniform flag selects a `device_load` path instead (RGB32 formats) | r32ui 1000/1000 exact, all 104 OOB indices return 0. r8 → `k/255` 256/256. rgba32f exact including NaN payloads, OOB = (0,0,0,0) |
| 3D / array images (`surf3D*`, layered surfaces) | `image_write ... tex_3d` / `tex_2d_array`; read back via `texture_load` mode `0b1101` | store→load r32ui 512/512 and 384/384 |

Out-of-range `texelFetch` returns zero **in the stored format**, and then the format swizzle still applies:
rgba8 OOB = (0,0,0,0), but r8 OOB = (0,0,0,1). CUDA's border/`tex1Dfetch` OOB contract is all zeros. For
single-channel textures CUDA returns a scalar, so the alpha=1 fill does not reach CUDA code.

## Follow-ups (same day)

| Question | Result |
|---|---|
| Buffer of 70000 texels (wider than one 16384 row) | 176/176 exact across every 16384-texel row boundary; OOB tail returns 0 |
| Mipmapped 2D array (4 levels x 4 layers) | level = `ceil(lod-0.5)` clamped, chosen per layer: 64/64 |
| Linear cube filtering at a face edge (+X/+Z, faces solid 20 / 180) | **seamless**: exactly 100 (50/50) on the edge, then linear to the face value over half a texel (65/65) |

## Simulator update

`AGX-Performance-Simulator/rust/src/texture.rs`: `sample_linear` now quantizes weights with `filter_weight`
(this rule) and treats R8 unorm like RGBA8 unorm on the 12-bit path. Half-float textures now round to fp16
(`round_f16`). A typo was also fixed: the float path had used `fy` in place of `fx` on the (1,1) tap. Unit test
`filter_weights_measured`; `cargo test --release` and `make verify-texture-unit` (4/4) pass.

## Not established

- The 3D 8-tap accumulation residual (5/448 near-tie lanes).
- Cube arrays, and cube corners (three faces meeting at one point).
- Anisotropic filtering, integer-format filtering (GL forbids it), and 1D textures (GLES has no 1D target;
  Mesa would use a 2D or buffer path).
- Gradient-derived LOD precision (`textureGrad`) beyond the 8 earlier points.
