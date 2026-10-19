# Texture unit in the simulator: state stores, PBE, store rounding (2026-10-19)

End-to-end texture/image execution in `AGX-Performance-Simulator` (`rust/src/func.rs`,
`rust/src/texture.rs`), driven by Mesa's recorded extracts (`texfetch`, `texfilter`,
`imgerode`, `imgtonemap`). Four new findings, all required to make the sim run:

## 1. `tex_state_store` / `sampler_state_store` address semantics

`agx_pack.c` packs `U = heap.value >> 2` at bits 59..62 and the offset-is-immediate
flag at bit 58. `hk_shader.c` `lower_uniforms` remaps descriptor set `s` to uniform
halves `4 + 4s`, so set 0's base is halves 4..7 (32-bit uniforms 2,3) and `U = 1`.
All recorded stores have `U = 1, bit58 = 1`: the `O` field is an **immediate in
half-words**, not a register — the disassembler's `r0`/`r12`/`r24` is a display
artifact (applegpu has no immediate variant for this operand). Verified offsets:
`O = 0` (binding 0 tex at set+0), `O = 12` (binding 0 sampler at set+24),
`O = 24` (binding 1 tex at set+48, stride 48). The sim errors on register offsets
(none observed).

## 2. Register-form sampler: `clamp_0 = -1` means "no override"

`texfilter`'s second sample takes its sampler from `r0h`, which the preamble fills
with the descriptor's `clamp_0` field (`-1` = no custom border, since the sampler
is clamp-to-edge). A negative value resolves to the descriptor's own sampler; with
one populated sampler slot that is unambiguous (implemented). A non-negative value
is a sampler-heap index (heap population is a harness gap, errored clearly).

## 3. Image stores address the PBE descriptor; strides carry Mesa's -16 bias

For slot-form `image_write` Mesa emits the **PBE** descriptor (`hk` lower-image:
writes go through PBE), decoded with a separate 24-byte layout (2-bit swizzles,
address shr 4, raw stride). Bindless direct-form `image_write` reads the texture
descriptor at `set + offset` (offset-in-binding 0 = tex, 24 = pbe; the 48-byte
`hk_storage_image_descriptor` stride). Both sampled-tex and PBE stride fields are
written by Mesa as linear pitch minus 16 (tex shr 4, PBE raw), so the sim uses
pitch = field*16+16 (tex) / field+16 (PBE) — self-consistent with synthesis that
writes pitch/16-1 / pitch-16, and validated by the value checks below.

## 4. `imageStore` float->unorm8 rounds half-to-even on the fp32 result

`imgtonemap`: 67/12288 color bytes sit exactly on a rounding tie; all go to even
(RTNE on the shader's fp32 Reinhard value), max diff 1, alpha kept. This matches
the hardware recording's profile (max_level_diff 1, 0.996 nearest). The exact-tie
rule at hardware level is consistent-but-not-proven; the ±1 tolerance covers it.

## Results (`make verify-texture-unit`, pure Python + `agx_run`, no GPU)

| workload | check | result |
|---|---|---|
| texfetch (r32f texelFetch, 256 lanes) | bit-exact incl. ±0, 3.4e38, min-normal | 256/256 |
| texfilter (RGBA8 linear/clamp, 512 uv) | exact-weight bilinear within 2/255 at best subtexel bits (4..10) | 10-bit bucket at 0.150/255 |
| imgerode (r32ui ping-pong erode, 4 dispatches) | bit-exact vs minima reference | 3072/3072 |
| imgtonemap (RGBA8 load/Reinhard/store) | within 1 level, alpha kept | 9216/9216 color, 0 alpha bad |

Also covered along the way: sampler `U`/`Tt` packing for bindless bases
(`sample_ureg` → `UReg64(2)` = set VA), `lod_min` immediates vs `uNl` halves,
the `image_write` operand order (coords tuple precedes the texture operand —
the `TexOp` parser is order-independent now), and `q3` (not the 2-bit `mode`)
selecting texelFetch (0b1100) vs image-load (0b1101) vs sample (0b1100).

Scope: 2D linear only; mipmapped sampling, border wrap modes, 1D/3D/array targets,
float16 stores, and register-offset state stores error clearly.
