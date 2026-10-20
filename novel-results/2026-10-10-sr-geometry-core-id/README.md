# SR7 SIMD-group count and SR20 cluster/core encoding

On the driver-reported Apple M2 Max G14C B1 / Mesa 25.3.6, compute stage:

- **SR7 = ceil(threads per threadgroup / 32).** This held in all nine tested
  local/group shapes (1, 24, 32, 42, 64 and 256 threads; 1-D to 3-D), on every
  lane, and stayed 1 over 2048 workgroups of 32. Neither the Mesa nor the applegpu
  SR table names it.
- **SR20 = `(cluster << 4) | core`.** Over 2048 workgroups on three fresh devices,
  it took exactly 38 values. That set equals `{(c<<4)|k : bit k of core_masks[c]}` from
  the driver's GET_PARAMS masks `0x3ff,0x1ff,0x1ff,0x3ff`, and SR20 was uniform within
  every workgroup. Mesa calls it `core_id`; the packed cluster/core layout and the match
  with the enabled-core masks are this project's observation.

Use for PTX: `%smid` → SR20 (sparse) or a mask-based dense remap; `%nsmid` = 38;
`%laneid` → SR52; per-block warp index → SR53; warps per block → SR7.

Also confirmed on hardware for 2-D/3-D shapes: SR0–2, 4–6, 48–53, 56–59 and 80–82,
as tabulated in the report. Negative result: the bit-15 `get_sr` encoding does not
write its destination or any SR observable through `get_sr`, for any of 256 selectors.

Proof: `make verify-sr-shape` checks the retained evidence against independent
oracles and runs failure injection. Hardware: `make sr-shape`, `make sr-core`.
[Report](../../experiments/registers/sr-geometry-core-alt.md) ·
[evidence](../../results/2026-10-10-sr-shape-core/README.md).
These are observations from one device, not claims of first community discovery.

The [2026-10-20 arithmetic placement study](../2026-10-20-integer-core-distribution/README.md)
confirms these 38 packed IDs and workgroup-uniform tags in 12 final maps of
1024 workgroups under arithmetic load. Matching SR19 twins report the declared
64 register halves exactly. This measures cumulative assignment, not
simultaneous residency or frequency.
