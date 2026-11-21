# Fragment tile → GPU core map, and what it does to render timing (M2 Max, 2026-11-21)

**Method.** Capture a full-screen pass from Mesa's open-source GLES driver and replay it with direct ioctls
(AGX-Performance-Simulator `tests/drm_render_replay.c`). The fragment program is replaced by our own assembled code,
`get_sr r0, sr20 (core_index)`, which writes the core ID into the pixel. The framebuffer is then read back through a linear PBE.
This was done for 30 screen sizes, from 32x32 to 1280x32 and 800x600 (`coremap_sweep.py`; raw grids in `maps.json`).
SR20 = cluster << 4 | core, with 38 cores in clusters of 10, 9, 9 and 10 (core masks 0x3ff, 0x1ff, 0x1ff, 0x3ff).

## Findings

| Item | Finding |
|---|---|
| Unit | Each 32x32 tile runs entirely on one core: in every size, no tile mixed core IDs. |
| Pairs | The two tiles of a horizontal pair (x = 2k, 2k+1) always share a core. |
| Blocks | Tiles go in blocks of 2x4 tiles. The 4 rows of a block take consecutive cores of one cluster, wrapping modulo the cluster's core count. |
| Small passes | Passes with up to 40 tiles use **cluster 0 only** (10 cores). 192x192 (36 tiles) puts 4 tiles on a core; 224x224 (49 tiles) uses 28 cores with 2 tiles each. The threshold lies between 40 (256x160 and 1280x32: one cluster) and 42 tiles (224x192: four). |
| Large passes | Block columns alternate between an even and an odd cluster. The screen is halved into the two cluster pairs, apparently along its longer block dimension (256x256: top half → clusters 2/3, bottom half → 0/1). |

The simple rule above, implemented as `raster::tile_core_map`, reproduces the busiest core's tile count exactly for 25 of
the 30 sizes. The other 5 come out 1-2 tiles high. The exact visiting order inside a cluster is not decoded: it is Morton-like
for 6x6 tiles and right-pair-first for single block rows.

## Timing consequence

The same alu24 shader, as a full-screen opaque quad, has fragment times that are not monotonic in screen size:

| Screen | Tiles | Busiest core | Fragment |
|---|---|---|---|
| 32x32 | 1 | 1 tile | 7.25 us |
| 64x32 … 128x128 | 2-16 | 2 tiles | 9.7 us |
| 192x192 | 36 | 4 tiles (cluster 0 only) | 14.4 us |
| 256x256 | 64 | 2 tiles | 9.75 us |
| 384x384 | 144 | 6 tiles | 19.8 us |

Shading time follows the busiest core's tile count. Using per-tile core-model time t, it is about t × (1.3 × tiles on the busiest
core + 0.48). The simulator now computes this load from the map (`raster::shade_loads`).

## Related findings the same day (AGX-Performance-Simulator `results/2026-11-21-render-ioctl`)

- **Partial renders are bimodal per process.** A dense pass either flushes (about 5x slower; the vertex time grows as well) or
  does not, consistently within a burst. Detection: point the command's `partial_bg` at the normal `bg` program. A partial
  render then clears instead of reloading, so pixels drawn before the flush vanish.
- **Primitive order changes fragment cost.** The same 8192-triangle grid costs 7.2 us in order and 12.5 us shuffled. The cost
  follows tile-list block fetches (about 113 ns per 64-primitive block per tile, latency bound, about 4 tiles in flight per core).
- **Tiny instances are slow in the vertex stage.** 512 instances of a 3-vertex draw take 13.7 us; the same geometry as one
  plain draw takes 9.4 us; instances of 9 or more vertices take about 9.5 us.
