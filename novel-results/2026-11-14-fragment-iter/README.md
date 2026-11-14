# Fragment varying interpolation (`iter`, `iterproj`, `ldcf`), first measurements (2026-11-14)

Probe `tests/gles_varying.c` (Mesa GLES 3.2, RGBA32F target, one triangle with arbitrary clip w and attribute values, optional
4x MSAA resolved by blit); shaders captured with `scripts/agx_capture.py`. `agx_capture.py` needs applegpu under
`/save/workspace/AGX_Probe/applegpu` (a symlink to `agx-notes/applegpu` was created for this).

## What Mesa compiles
| GLSL | AGX |
|---|---|
| smooth `in vec4`/`vec2` | `iterproj rD.., cfI, cfJ, center` : 4 channels `count=0` (D 32-bit regs), numerators cf1.., 1/w plane cf0 |
| `centroid` | same, interpolation field = centroid |
| `flat` | `ldcf rN, cfK` (the C of the triple) + ALU per channel |
| 4x MSAA | identical fragment instruction (per-sample work is in the epilogue / tile store) |
Fragment outputs are plain registers; the colour write is a separate driver-generated shader (`st_tile`, `image_write_block`).

## Hardware results (64x64, three vertices at (-0.9,-0.8), (0.8,-0.7), (-0.2,0.9))
- Coverage (pixel centres, top-left rule as GL) matches an exact double-precision edge test on every pixel (1446 / 1446, 0 edge mismatches), with w = 1 and with w = 1, 2, 0.5.
- w = 1: each channel is an exact plane A*x + B*y + C of the pixel-centre coordinates (x + 0.5, y + 0.5): least-squares residual <= 5.4e-7 absolute, mean 1-3 ulp (fp32 rounding of the evaluation).
- Against the exact barycentric values the hardware differs by up to 5e-4 absolute: the rasterizer snaps vertices to fixed point before computing coefficients, so coefficients cannot be derived from the float vertices; the simulator takes them as input.
- w != 1: not a plane (perspective); consistent with numerator plane / (1/w) plane (`iterproj`).

## Simulator
`agx_run --frag FILE` (rust/src/frag.rs, `fsem::frag_iter`): `scripts/frag_iter_check.py` replays the captured `iterproj` over 32 lanes x 4 channels, max 4.8e-7 from the hardware pixels (coefficients fitted from the same image). Open items: tasks/render-02-fragment-isa.md in AGX-Performance-Simulator.
