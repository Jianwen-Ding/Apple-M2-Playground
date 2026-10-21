# B29: texture corners for ZLUDA's native path (2026-10-21)

Blocker B29 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), Mesa GLES compute
(`scripts/run_gles_b29.py`, harness `tests/gles_compute.c` gained `d32f`, `rgba8ui/i`, `rgba16ui/i`, `GLES_TEX_COMPARE`,
`GLES_TEX_MINLOD/MAXLOD`); Mesa builds all state, nothing hand-encoded; 21 cases, guards intact, 0 faults.
`analysis.txt` holds the fits.

## Already answered by earlier findings (probes 1, 2, 3, 6, 8)

- **1, filter weights:** 1/256 steps (`w = floor(frac*256 + 0.5)/256`, `2026-10-20-texture-targets`): CUDA's 1.8 fixed point.
- **2, normalized reads:** unorm8 `k/255`, snorm8 `max(k/127, -1)` (-128 and -127 give -1), unorm16 `k/65535`, snorm16
  `max(s/32767, -1)` (`2026-10-18-gles-texture`, `2026-10-19-texture-edge`).
- **3, border:** arbitrary float and integer border colours, quantized to the texture format (`2026-10-19-texture-edge`;
  `VK_EXT_custom_border_color` is exposed).
- **6, cubemaps:** face selection in hardware, ties x > y > z; seamless filtering across faces (`2026-10-20-texture-targets`).
- **8, gather:** footprint `(ceil(c) - 1, ceil(c))` per axis and the component order (`2026-10-19-texture-edge`).

## New (this run)

| Probe | Result |
| --- | --- |
| 7, depth compare, nearest | **`result = ref OP texel`** for all 8 functions (64 / 64 each; the reversed order fits only 16 / 64 for the ordered ones) |
| 7, depth compare, linear | **PCF**: each tap is compared, then the 0 / 1 results are filtered (results in 1/16 steps for 1/16 sub-texel offsets) |
| 5, `textureGrad` | **lambda = log2(max(\|dPdx\|, \|dPdy\|) * size)** with the Euclidean length of each gradient (diagonal gradients fit the length within 0.008, the max component misses by 0.5); within the 1/64 level-weight quantum |
| 5, MIN_LOD / MAX_LOD | **clamp the LOD before level selection**: trilinear results stay in [1.5, 3.25]; nearest-mip picks levels 1..3 (`ceil(lod - 0.5)` of the clamped value) |
| 10, float -> unorm8 store | round to nearest, clamp to [0, 255] (3,072 / 3,072) |
| 10, float -> snorm8 store | clamp to [-127, 127], round to nearest (2,560 / 2,560) |
| 10, out-of-range integers into rgba8ui / rgba8i / rgba16ui / rgba16i | **saturate** (1,024 / 1,024 each; wrap fits 41-676) |

The LOD-bias order (bias is not available in GLES compute) was not tested.

## Not run yet (prepared)

Probes **4** (unnormalized coordinates with clamp / border) and **9** (pitch-linear images at explicit row pitches) need
Vulkan: `tests/vulkan_texture.c` + `scripts/run_vk_b29.py` are written and build, not run. From Mesa's descriptor
definitions: a linear texture's stride field is 18 bits in 16-byte units (minus 1 encoded), so any 16-byte-multiple
pitch up to 4 MiB, which covers CUDA's 32-byte pitch alignment; the sampler has a "Pixel coordinates" bit for
unnormalized coordinates.
