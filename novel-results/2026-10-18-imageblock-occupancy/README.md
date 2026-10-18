# Imageblock layouts do not consume threadgroup memory: occupancy depends only on the declared bytes

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage. Answers the new question of safe-11 section 2 for the
[SR12 / SR13 / SR15 imageblock finding](../2026-10-11-sr12-sr13-sr15-imageblock/README.md): "do tile memory and threadgroup memory share the 64 KiB per
core?" Only the 12 USC Shared words that ran cleanly in that finding; the occupancy program of the
[occupancy follow-ups](../2026-10-18-occupancy/README.md) (per-core counter, atomic max, no loops). 0 faults.

## Test

Each Shared word of the imageblock finding sets an imageblock layout (width x height 32x32, 32x16 or 16x16; sample stride; sample count) and a
threadgroup bytes field (declared bytes = field x 256, field 0 = 64 KiB). For each word the occupancy counter ran with 128-lane workgroups and 16
declared register halves, once with the word and once with a plain-layout word (layout 0x24) carrying the same bytes field. 3 repeats = 72 runs.

## Result

* **All 36 imageblock / plain pairs gave identical peak resident SIMD groups.** An imageblock layout does not take threadgroup memory beyond the bytes it
  declares.
* **The peak is `4 x floor(65536 / bytes)` groups** in every run (8 KiB: 32, 16 KiB: 16, 24 KiB: 8, 32 KiB: 8, 56 KiB: 4, 64 KiB: 4), the formula of the
  occupancy findings. The layout fields (32x32 / 32x16 / 16x16, sample stride 0-15, sample counts) change nothing: the three layouts at 8 KiB all give 32.
* So for a compute dispatch the 64 KiB per core are threadgroup memory only, as far as occupancy shows; whether a fragment / tile dispatch with a real imageblock
  uses a separate tile memory was not tested.

Not established: fragment-stage behaviour, and whether the imageblock bytes (not the layout fields) of a tile dispatch count against the same 64 KiB (the Shared
words here declare threadgroup bytes only; the imageblock stride is a layout field).

## Reproduce

`python3 scripts/run_drm_imageblock_occ.py hardware`; `make verify-imageblock-occ` (offline, 4 checks against
[results/2026-10-18-imageblock-occupancy](../../results/2026-10-18-imageblock-occupancy)).
