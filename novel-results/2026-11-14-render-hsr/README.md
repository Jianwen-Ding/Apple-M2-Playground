# Render path, first measurements: hidden-surface removal and fragment ALU rate (2026-11-14)

Probe: `tests/gles_raster.c` (surfaceless EGL, GLES 3.0 through Mesa's open-source asahi driver, no vendor tools).
It draws `layers` full-target quads into a 1024x1024 RGBA8 renderbuffer; `RASTER_FLUSH=1` flushes per frame and a
1-pixel `glReadPixels` ends each repetition (`RASTER_KEEP=1` keeps the tile store). Data: `sweep1.jsonl`. M2 Max, idle GPU.

## Pitfalls (these made the first runs meaningless)
- Without a per-frame `glFlush`, 50 `clear + draw` frames cost 0.02 ms each: the driver drops draws a later full clear
  makes redundant. A render probe needs a flush (or a read) per frame, as a compute probe needs back-to-back commands.
- `glRenderbufferStorageMultisample(samples=1)` makes a real multisampled target (`glReadPixels` then gives
  GL_INVALID_OPERATION); pass 0 for single-sample.
- `glInvalidateFramebuffer` after the draws lets the pass skip the tile store (kept off here).

## Findings (1024x1024, 2 triangles per layer, ms per frame)
| fragment ALU iterations (2 dependent fma each) | layers | blend | ms |
|---|---|---|---|
| 256 | 1 | off | 0.411 |
| 256 | 8 | off | 0.415 (**8 opaque layers cost the same as 1: hardware hidden-surface removal**) |
| 256 | 1 | on | 0.418 |
| 256 | 8 | on | 3.180 (7.6x: blending defeats HSR, every layer shades) |
| 64 / 256 / 1024 | 1 | off | 0.134 / 0.411 / 1.514 (linear in ALU beyond a ~0.05 ms floor: 1.44 ps per pixel-iteration) |
| 1 | 1 / 8 | on | 0.055 / 0.092 (cheap shader: overdraw is bandwidth/tile-memory bound, not ALU) |

Implication for the simulator: a render model must (a) shade only visible fragments for opaque, depth-tested, non-discarding
shaders, (b) shade every covering fragment when blending, discarding, or writing depth/sample-mask from the shader, (c) add a
fixed per-pass floor (~0.02-0.05 ms here).
Open: what exactly turns HSR off (discard, alpha-to-coverage, depth write, translucent order), tile size and bin cost,
vertex-bound behaviour (small triangles), MSAA, tile load/store cost, 2x2 quad inefficiency at triangle edges.
