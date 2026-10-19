# Mesa texture/sampler descriptors and the bindless path on AGX (Honeykrisp)

How a Vulkan `OpImageFetch`/`OpImageSample*` becomes AGX state, traced end to end through the
Mesa 25.3/26.0 sources vendored in `AGX_Probe/mesa`. This is the reference for the simulator's
texture unit and for any ZLUDA-side descriptor work. No GPU probing was needed: every claim is
source-backed, with the exact file:line.

## Big picture (all bindless)

Honeykrisp makes **everything** bindless (`hk_nir_lower_descriptors.c:602+`). A texture/sampler
pair becomes a 64-bit handle = `set_base_VA + binding_offset + plane*64`, resolved at shader
build time into a `nir_bindless_*_agx` intrinsic. The backend (`agx_compile.c:796`)
splits it into a uniform holding the set base and an offset. The preamble writes hardware state
from those, and the main shader's `texture_*` instructions reference plain `ts#`/`ss#` slots.
Nothing texture-specific remains in the main shader except the slot numbers.

## The descriptor structs (`hk_descriptor_set.h:21-52`)

| Struct | Size | Contents |
|---|---|---|
| `hk_sampled_image_descriptor` | 64 B | `agx_texture_packed tex` (24 B), `agx_sampler_packed` (8 B), `sampler_index` u16 (heap index + 28), `clamp_0_sampler_index_or_negative` i16, `lod_bias_fp16`, `min_lod_fp16`, plane padding |
| `hk_storage_image_descriptor` | 48 B | `agx_texture_packed tex` (24 B), `agx_pbe_packed` (render backend) |

Per-binding stride = struct size × plane count (sampled 64 B, storage 48 B, buffer addresses 16 B),
bindings laid out in order with alignment = stride (`hk_descriptor_set_layout.c:195-260`).

## `agx_texture_packed`: the 24-byte hardware descriptor (`genxml/cmdbuf.xml`, struct `Texture`)

Bitfields below are [start:size]; `minus(1)` = stored value is dim-1, `shr(4)` = stored value is
bytes >> 4 (16-byte granule).

| Bits | Field | Notes |
|---|---|---|
| 0:4 | Dimension | 2D=2, 2D array=3, 3D=5, Cube=6 (enum `Texture dimension`) |
| 4:6 | Layout | Linear=0, Twiddled=1 (`Layout`) |
| 6:13 | Channels | format: R8=0x00, R32=0x21, R16G16=0x23, R8G8B8A8=0x28, R32G32=0x31, R16G16B16A16=0x32, R32G32B32A32=0x38 (`Channels`) |
| 13:16 | Type | Unorm=0, Snorm=1, Uint=2, Sint=3, Float=4 (`Texture Type`) |
| 16:28 | Swizzle R/G/B/A | 3 bits each (`Channel`: R=0 G=1 B=2 A=3 1=4 0=5) |
| 28:42 / 42:56 | Width / Height | minus(1) |
| 56:60 / 60:64 | First / Last level | mip range; single level = 0/0 |
| 64:66 | Samples | multisample count |
| 66:102 | Address | shr(4): GPU VA >> 4 (36 bits cover a 48-bit VA) |
| 102 / 103 | Unk mipmapped / Compressed | |
| 104:106 | Mode | Normal=0 (`Image Mode`) |
| 106:108 | Compression | |
| 108 / 109 | sRGB / sRGB 2-channel | |
| 110:128 | Stride | shr(4): row pitch in bytes >> 4 (linear layouts) |
| 126 / 127 | Page-aligned layers / Extended | |
| 128:192 | variant | acceleration buffer (compressed) *or* linear depth/layer-stride *or* sw buffer size/offset (buffer textures) |

Filled by `hk_image_view.c:240+` (`agx_pack(out, TEXTURE, cfg)`): address = base + layer/level offset,
width/height = (minified) pixels, sRGB flag from the format, swizzle = format◦view swizzle.
`agx_set_null_texture` (`lib/agx_helpers.h:221`) zeroes a descriptor (all-zero except fields that
must be set for a null bind).

## The 8-byte sampler (`genxml/cmdbuf.xml`, struct `Sampler`)

| Bits | Field | Notes |
|---|---|---|
| 0:10 / 10:20 | Minimum / Maximum LOD | 10-bit `lod` fixed-point |
| 20:23 | Maximum anisotropy | log2 |
| 23:25 / 25:27 / 27:29 | Magnify / Minify / Mip filter | 0 = Nearest, 1 = Linear (Mip: 0 = None, 1 = Nearest, 2 = Linear) |
| 29:32 / 32:35 / 35:38 | Wrap S / T / R | 0 = clamp-to-edge, 1 = repeat, 2 = mirrored repeat, 3 = clamp-to-border, 4 = GL clamp |
| 38 | Pixel coordinates | unnormalized-coords samplers |
| 39:42 + 42 | Compare func + enable | shadow samplers |
| 55:57 | Border colour | 0 = transparent black, 1 = opaque black, 2 = opaque white, 3 = custom |
| 57 | Seamful cube maps | |

`hk_sampler.c` builds these from `VkSamplerCreateInfo` (filter/mipmapMode/addressMode → fields;
border colour enum → custom only if the colour is not one of the three fixed). Binding a sampler
puts it on the device-wide **sampler heap** (`hk_device.c:148+`); descriptors reference it by
heap index + 28 (`hk_descriptor_set.c:109+`).

## Preamble → state slots → shader (`agx_compile.c:790-834`, ISA `AGX2.xml:1382-1397`)

- `nir_load_preamble(desc_set)` + binding offset ⇒ 64-bit handle (uniform base + offset reg).
- Preamble: `tex_state_store tsN, uB, rO` — **the 24-byte descriptor at MEM[uB+rO] is stored
  into texture state register tsN** (`applegpu.py:4816`, size 8, dest TS bits 8:14, B = ureg64
  bits 58:63, O = reg bits 27:33). `sampler_state_store ssN, uB, rO` does the same for the
  8-byte sampler.
- Main shader: `texture_load` / `texture_sample` / `image_*` take plain `ts#` / `ss#` indices.
  Observed encodings (all Mesa-emitted): `texture_load` mode `0b1100` (texelFetch) and `0b1101`
  (imageLoad, with bit 43 set plus bit 46 for coherency); `texture_sample` carries the LOD mode
  (`lod_min`, `lod_grad`); `gather_r` for `textureGather`.

## What the simulator needs (and does)

`func.rs` implements the two store ops (24 B / 8 B into per-dispatch slot files), decodes the
slot contents with exactly the tables above, and executes sampling with the playground-measured
conversion/filter rules (`texture.rs`, `novel-results/2026-10-18-gles-texture`,
`novel-results/2026-10-19-texture-edge`). Texel memory comes from the workload's known buffers,
mapped at sim VAs; descriptors are synthesized with those VAs (same Mesa layout). No driver
byte is trusted: every field the sim reads is validated against the tables above, and every
sampled value is checked against hardware recordings.

## Open Mesa-side questions (not needed for the sim)

- Exact `lod` 10-bit fixed-point format and the `Unk mipmapped` bit 102 semantics.
- Whether `ts#` slots hold the descriptor bytes or a VA to them (sim treats them as bytes per
  applegpu's doc; both behave identically once synthesized).
- Compressed-format descriptor variants (tiling/compression fields) — out of scope for CUDA.
