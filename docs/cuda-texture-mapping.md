# CUDA texture / surface operations against AGX (safe-05 step 4)

Evidence level per row: **measured** = run on the M2 Max through Mesa GLES
([findings](../novel-results/2026-10-18-gles-texture/README.md),
[edge findings](../novel-results/2026-10-19-texture-edge/README.md));
**expected** = follows from Mesa's choice of instruction for the matching GLSL
operation, not run; **open** = no evidence. Mesa builds all descriptor state; the descriptor word layout is not documented here.

| CUDA | Closest GLSL / Mesa operation | AGX instruction | Status |
|---|---|---|---|
| `tex2D` point filter, unnormalised or normalised coords | `textureLod`, nearest | `texture_sample` (sampler state `ss`) | measured: clamp, repeat, mirror exact; OOB `texelFetch` returns 0 |
| `tex2D` linear filter | `textureLod`, linear | `texture_sample` | measured: result = `floor(exact*16+0.5)/4080` for unorm8 (12-bit rounding); CUDA's own 8-bit weight rule differs, so results will not match bit for bit. Blends into a quantized border under the same rule |
| `tex2D<float>` on unorm8 / snorm8 / sRGB | same | `texture_sample` / `texture_load` | measured: `k/255`, `max(k/127,-1)`, `round(srgb*4095)/4095`; sRGB bilinear filters 12-bit taps and rounds the result to 1/4095 |
| `tex2D` on half / float / integer formats | `texelFetch` | `texture_load` | measured: r16f (all 65,536), r32f, rgba32f, r8ui, r32ui, r16, r16snorm, r16ui exact |
| `tex2DLod`, `tex2DGrad` | `textureLod`, `textureGrad` | `texture_sample` (`lod_min` / `lod_grad` modes) | measured 2026-10-19: nearest level = ceil(lod-0.5) clamped (ties down); trilinear = float32-exact adjacent-level blend; grad lod = log2(max texel-gradient) |
| `tex1D`, `tex3D`, `tex2DLayered`, cube | 1D / 3D / array samplers | `texture_sample` with other target kinds | open |
| address mode border | clamp-to-border | sampler state | measured 2026-10-19: float borders quantize to the texture format (0.5 -> 128/255 on r8); integer borders exact (0x12345678 on r32ui) |
| `tex1Dfetch` (linear memory) | `texelFetch` on a buffer texture | `texture_load` | open |
| `tld4` (gather) | `textureGather` | `texture_sample ... gather_r ...` | measured 2026-10-19: footprint box (ceil-1, ceil) per axis, order ((x0,y1),(x1,y1),(x1,y0),(x0,y0)), edge-clamped |
| `surf2Dread` | `imageLoad` | `texture_load` (mode word 0b1101) | measured: rgba8 unorm and r32f |
| `surf2Dwrite` | `imageStore` | `image_write` (`rte`) | measured: r32f round trip bit exact; unorm8 store is RTNE on the fp32 value (ties to even, max diff 1) |
| surface clamp / trap / zero modes | none in GLSL | none | open: GLSL has no equivalent; ZLUDA would need explicit bounds code |
| texture objects (64-bit handles) | descriptor table index | texture / sampler slots `ts` / `ss` | simulator model exists: set base in uniforms 2+2s, 64B sampled / 48B storage descs, bindless = base + offset; sampler-heap population is a harness gap |

Unsupported or unmodelled: bindless sampler-heap population, CUDA's 1.8-fixed-point linear weights, `tex.level` with non-default modes beyond the measured `lod_min`/`lod_grad`, surface bounds-mode
traps, 1D/3D/array/cube targets. Anything marked open needs a Mesa-compiled GLSL probe first (never hand-encoded state).
