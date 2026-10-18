# CUDA texture / surface operations against AGX (safe-05 step 4)

Evidence level per row: **measured** = run on the M2 Max through Mesa GLES
([findings](../novel-results/2026-10-18-gles-texture/README.md)); **expected** = follows from Mesa's choice of instruction for the matching GLSL
operation, not run; **open** = no evidence. Mesa builds all descriptor state; the descriptor word layout is not documented here.

| CUDA | Closest GLSL / Mesa operation | AGX instruction | Status |
|---|---|---|---|
| `tex2D` point filter, unnormalised or normalised coords | `textureLod`, nearest | `texture_sample` (sampler state `ss`) | measured: clamp, repeat, mirror exact |
| `tex2D` linear filter | `textureLod`, linear | `texture_sample` | measured: result = `floor(exact*16+0.5)/4080` for unorm8 (12-bit rounding); CUDA's own 8-bit weight rule differs, so results will not match bit for bit |
| `tex2D<float>` on unorm8 / snorm8 / sRGB | same | `texture_sample` / `texture_load` | measured: `k/255`, `max(k/127,-1)`, `round(srgb*4095)/4095` |
| `tex2D` on half / float / integer formats | `texelFetch` | `texture_load` | measured: r16f (all 65,536), r32f, rgba32f, r8ui, r32ui exact |
| `tex2DLod`, `tex2DGrad` | `textureLod`, `textureGrad` | `texture_sample` (lod modes) | open: only `lod_min` form seen |
| `tex1D`, `tex3D`, `tex2DLayered`, cube | 1D / 3D / array samplers | `texture_sample` with other target kinds | open |
| address mode border | clamp-to-border | sampler state | open |
| `tex1Dfetch` (linear memory) | `texelFetch` on a buffer texture | `texture_load` | open |
| `tld4` (gather) | `textureGather` | unknown | open |
| `surf2Dread` | `imageLoad` | `texture_load` (mode word 0b1101) | measured: rgba8 unorm and r32f |
| `surf2Dwrite` | `imageStore` | `image_write` (`rte`) | measured: r32f round trip bit exact; unorm8 store rounding not measured |
| surface clamp / trap / zero modes | none in GLSL | none | open: GLSL has no equivalent; ZLUDA would need explicit bounds code |
| texture objects (64-bit handles) | descriptor table index | texture / sampler slots `ts` / `ss` | open: no handle-to-slot model |

Unsupported or unmodelled: bindless handle semantics, CUDA's 1.8-fixed-point linear weights, `tex.level` / `.grad` forms, gather, surface bounds-mode
traps. Anything marked open needs a Mesa-compiled GLSL probe first (never hand-encoded state).
