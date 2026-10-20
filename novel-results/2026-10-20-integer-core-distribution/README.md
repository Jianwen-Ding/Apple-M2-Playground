# Arithmetic trains use all 38 cores, with a dispersed tail of workgroups

M2 Max G14C B1, direct DRM, AC online, 2026-10-20. **28 bounded trains /
1608 dispatches**, zero faults. All arithmetic words and guards are exact;
14 SR19 final buffers match literal scalar expectations, 14 SR20 final maps
pass complete placement-property checks, and all 56 recovery controls are
exact. Physical core tags are not expected to equal default simulator placement.

Following the [length study](../2026-10-20-integer-length-cost/README.md),
append a separate output plane to the same ordinary immediate-add programs.
Matched twins differ only in the selector of one four-byte get_sr instruction:
SR19 reports the 64-half register allocation; SR20 reports packed core identity.
Code length, arithmetic body, output footprint, declared allocation and launch
settings match. The new read uses r30, within the existing 64-half allocation,
after the arithmetic results have been stored.

Four 32-lane / 4096-add / four-submit pilots preceded the full matrix. The
matrix has 131072 lanes, workgroups of 128, 1/8 chains, 1024/4096 adds,
both selectors, three interleaved trials and 64 submissions per train, with
the established 1000 us host delay. Full scalar/simulator gates pass before
hardware, including successive table states. Intermediate buffers are not
captured; each retained map describes the buffer after the final dispatch.

Every full-size SR20 record contains all 38 known core IDs. Every lane has a
valid tag under masks 3ff/1ff/1ff/3ff, and every workgroup has one uniform core
ID. Each map accounts for exactly 1024 workgroups. Peak cumulative workgroup
counts on one core vary as follows; they are not simultaneous residency:

| Chains | Adds | Cores seen in every trial | Busiest-core counts, trials 0/1/2 |
| --- | --- | --- | --- |
| 1 | 1024 | 38 | 28 / 28 / 29 |
| 1 | 4096 | 38 | 33 / 33 / 32 |
| 8 | 1024 | 38 | 29 / 28 / 29 |
| 8 | 4096 | 38 | 31 / 31 / 32 |

The default model estimates 27 workgroups on its busiest representative core.
The observed cluster totals are 240, 248, 256, 264 or 272 workgroups: all
multiples of eight across these 12 full-size maps. This fixed-geometry result
does not establish a general scheduling granule. Individual used cores receive
23–33 workgroups. The full maps and all timing samples are retained.

SR20/SR19 pooled last-quarter timing ratios are 0.9873, 1.0073, 0.9942 and
1.0036 for the four rows: within 1.3% of equal. The selector change does not
explain the broad timing gap. All 38 cores appearing in a final map also
does not establish that all 38 were executing simultaneously.

The simulator now accepts an explicit measured peak via
`--busiest-core-wgs N` / `Launch::busiest_core_wgs_override`. It changes the
representative core's waves and launch work; distinct workgroups are sampled
over the grid for that count. It does not reconstruct actual workgroup IDs,
core identities, a full placement map, concurrent residency or clock state.
The valid count range is ceil(workgroups / cores) through workgroups, checked
before reading shader or mapped files. The output echoes the supplied input.

Using each final map's measured peak increases the model prediction by
0.35–17.35%. The corresponding final-dispatch hardware duration still exceeds
that prediction by 2.76–3.06x. This is a placement-sensitivity calculation,
not a fitted latency or a claim that the complete observed schedule is modelled.
All eight default predictions match outputs retained before the change, and
no global timing calibration changed.

Next, vary workgroup geometry under the same tagged, controlled-gap protocol
to test core/cluster assignment and the observed cluster-count multiples.
Actual operating frequency and the remaining throughput gap remain open.

[Evidence, CPU corruption checks and offline verification](../../results/2026-10-20-integer-core-distribution/README.md).
