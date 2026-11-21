# AGX raster path decoded with direct ioctls (2026-11-21)

M2 Max G14C, Asahi 6.19.14, idle GPU, top clock (clock-keeper warm-up). Passes captured from Mesa's open-source GLES driver,
replayed through `DRM_IOCTL_ASAHI_SUBMIT` with no Mesa in the loop, then mutated: state words, vertex data, our own assembled
fragment code. Full tables, tooling and simulator accuracy: AGX-Performance-Simulator
`results/2026-11-21-render-ioctl/README.md` and `tasks/render-03-raster-model.md`.

## New facts about AGX
- **Fragment SIMD group** = 8x4 pixels as 2x2 quads, four across: lane = 4·quad + 2·(y&1) + (x&1).
  - sr0 / sr1 hold the tile (32x32) coordinates.
  - sr53 numbers a tile's groups by 16x16 quadrant (TL, BL, TR, BR).
  - Edge blocks of adjacent triangles mostly share one group (triangle merging): 34 groups instead of 32 per edge tile.
- **Rasterizer** snaps vertices to **1/256 pixel**. Coefficient planes are fitted to the snapped vertices.
- **Coefficient registers** hold C as the value at the **tile origin**, so varyings are evaluated in tile-local coordinates:
  - `iter` returns exact A·x + B·y + C **rounded toward zero**.
  - `iterproj` is within ±2 ulp of the exact ratio.
  - A constant plane has A = B = the smallest denormal.
- **Facing and fill rule:** with `Cull.Front face CCW`, the positive-area winding (top edge +x, left edges −y) is the back face.
  Fill follows the top-left rule. Off-screen vertices are rasterized exactly (guard band); only the near plane is clipped.
- **HSR is selected by the pass type in Fragment control 2** (Mesa keeps Fragment control 1 at Opaque):
  - Opaque = deferred, only the last covering fragment per pixel is shaded.
  - Translucent (blend) and Punch through (discard, gl_FragDepth) shade in order.
  - Flipping the field by ioctl moved a blended 8-layer pass from 691 to 96 µs, and its image to a single layer.
- **PBE linear stride** is in whole 16-byte rows: pitch = ((field >> 4) + 1) · 16.
- **End-of-tile `image_write_block`:** `q0 = 0` (EOT form) ignores the coordinate operand.
- **Depth surface "GPU" tiling** = 64x64-element tiles (4 B), Morton order inside, x in the even bits; decoded by a 12-replay
  bit sweep. Compression uses 16x16-pixel blocks with one metadata byte per 8x4 sub-block: 3 = constant sub-block (value in
  word block·256 + sub-block); all-zero metadata loads as 1.0.
- **Partial renders** (~1500+ triangles) reload the target through the partial-background program's texture descriptor.
- **Timing at the top clock:**
  - vertex stage ≈ 6.8 µs fixed + ~1 ns per screen tile + ~42 ns per draw, saturating in vertices;
  - fragment stage ≈ 3.2 µs fixed + max(10.6 ns per processed tile, shading);
  - 8 opaque layers cost the same as 1; a blended layer costs its full shading;
  - shading is 1.21x the calibrated compute core model, plus a per-core tail of ~2.8 tiles.

## Hazard (also in notes/failed-approaches.md)
- **SIGKILL of a process with GPU commands in flight** (the clock keeper's `drm_compute`): gCDM_CS unmapped faults, then about
  1000 GPU recoveries a second for 3 minutes. The GPU came back. Stop such processes gracefully.
