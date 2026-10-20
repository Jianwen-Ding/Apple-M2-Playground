# Aligned eight-workgroup blocks stay within one cluster across the tested 1-D geometries

M2 Max G14C B1, direct DRM, AC online, 2026-10-20. **160 bounded trains /
9600 dispatches**, zero faults. All arithmetic words and guards are exact;
80 SR19 final buffers match literal expectations, 80 SR20 final maps pass
complete placement-property checks, and all 320 recovery controls are exact.
Intermediate candidate buffers are not captured.

The [preceding placement study](../2026-10-20-integer-core-distribution/README.md)
used 128-lane workgroups. Host-only examination of its 12 final maps found that
every aligned block of eight consecutive workgroup IDs stayed within one
cluster. The new matrix tests other workgroup sizes and partial final blocks,
without treating that pattern as a hardware oracle requirement.

Sixteen one-workgroup pilots cover 32/64/128/256 lanes, 1/8 arithmetic chains
and matched SR19/SR20 tags. The 48 full-program gates all pass before timing.
The matrix crosses six geometries with both chain counts, 1024/4096 positive
immediate-1 adds, both selectors and three interleaved trials. Every full-size
train has 64 submissions and 1000 us added host sleep. Code bytes and memory
footprints are identical across the four fixed-lane-count workgroup sizes;
matched tag twins differ only in one get_sr selector. Allocation is 64 halves.

All **72 full-size SR20 maps** contain all 38 known core IDs. Tags are uniform
within every workgroup, valid under the enabled-core masks, and account for
every lane. Across every map, each aligned block of eight workgroup IDs has
one cluster ID, including the shorter final block. Every map has at least one
mixed aligned block of 16, so eight is the largest universally uniform width
among the tested powers of two from 1 through 128.

| Lanes | Workgroup size | Workgroups | Final maps | Final block length |
| --- | --- | --- | --- | --- |
| 131072 | 32 | 4096 | 12 | 8 |
| 131072 | 64 | 2048 | 12 | 8 |
| 131072 | 128 | 1024 | 12 | 8 |
| 131072 | 256 | 512 | 12 | 8 |
| 130944 | 128 | 1023 | 12 | 7 |
| 131200 | 128 | 1025 | 12 | 1 |

This is a workgroup-count pattern in these tests: the eight-workgroup block
contains 256/512/1024/2048 threads at the four sizes. A fixed 1024-thread
block hypothesis fails at sizes 32 and 64. Cluster totals have gcd 8 for the
four complete-block grids, but gcd 1 for the neighboring partial-block grids.
The aligned-block property survives those partial tails; aggregate totals
alone would miss it. Adjacent blocks may use the same cluster. This does not
establish a unique hardware packet format, temporal order, simultaneous
residency, or a rule for other sizes or multidimensional launches.

For the fixed 131072-lane grid, the model's default and observed peak
cumulative workgroup counts are:

| Workgroup size | Default busiest core | Observed busiest core |
| --- | --- | --- |
| 32 | 108 | 113–119 |
| 64 | 54 | 57–62 |
| 128 | 27 | 28–33 |
| 256 | 14 | 15–16 |

The table below pools each SR20 cell's final 16 samples from three trials;
times are microseconds. Every timing sample and quarter distribution remains
in the analysis.

| Workgroup size | 1 chain, 1024 adds | 1 chain, 4096 adds | 8 chains, 1024 adds | 8 chains, 4096 adds |
| --- | --- | --- | --- | --- |
| 32 | 86.500 | 329.958 | 98.312 | 343.229 |
| 64 | 81.105 | 309.000 | 90.688 | 324.583 |
| 128 | 82.270 | 321.000 | 90.000 | 330.875 |
| 256 | 86.751 | 316.312 | 94.541 | 331.166 |

Across all 24 paired cells, pooled SR20/SR19 ratios span 0.9908–1.0079.
Using each map's measured peak in the simulator still leaves a 2.67–3.42x
residual for the matching final dispatches on the fixed-lane-count grid.
That calculation samples representative workgroup paths; it does not replay
the observed placement map or change instruction latency.

The host-gap protocol is not a general guarantee of stable timing. The
fixed-lane-count cells' trial-median spreads reach 6.47%. At 130944 lanes /
128-lane workgroups / eight chains / 1024 adds, the SR20 trial late medians
are 89.771, 90.041 and 40.292 us, a 2.23x range despite identical code, inputs
and host-delay setting. The complete corpus's final-dispatch/model residuals
therefore span 1.19–3.42x. Retain this faster state; do not tune a global cost
from pooled timing alone. Operating frequency remains unmeasured.

Next, add an optional observed-core-map input to functional simulation, so
retained SR20 outputs can be replayed literally without inventing a predictive
scheduler. Preserve the existing default and synthetic stress modes and bind
historical and current model versions separately. The eight-workgroup rule
is a measured constraint for these 1-D shapes, not a complete schedule.

[Evidence and offline verification](../../results/2026-10-20-integer-geometry-cost/README.md).
