# Observed-map cost integration audit

2026-10-20, host-only source inspection after simulator commit `32eab2f`.
Prepared functional traces now carry observed SR20 identities. Passing such a
tracer directly into the existing `dispatch::simulate_with` is insufficient
for an observed-map cost path, for these concrete reasons:

- `wg_at` selects `(first+i)*cores` in the default path, or
  `floor((first+i)*N/peak)` with a scalar peak override. Neither selects the
  actual workgroups assigned to one supplied core. A wave assembled this way
  can mix different physical cores while the issue model treats it as one.
- The memory model uses `active_cores = min(configured_cores, N)`. An observed
  map may use fewer cores. Its footprint calculation multiplies one sampled
  core's distinct segments by this count and extrapolates waves; that is not
  the observed dispatch's exact segment union.
- Cross-core overlap samples grid IDs 1, 2, cores/2 and cores-1. With supplied
  state those IDs can share the selected core, so they are not necessarily
  cross-core samples.
- The cost model simulates its first and last assumed waves, extrapolating
  intermediate waves. Core identity does not establish arrival order,
  simultaneous residency, hardware slots or cross-workgroup memory state.
- The longest core time can belong to a core with fewer, more expensive
  workgroups. A supplied histogram's busiest count alone cannot select it for
  data-dependent programs.

Next implementation should use a separate explicit supplied-map path and
preserve default/scalar-peak results. Partition all linear workgroup IDs by
enabled packed core ID before selecting any wave. Validate map geometry and
core masks before tracing or preamble execution; reject simultaneous scalar
peak and full-map inputs rather than silently overriding one. Report each
partition's IDs/count, actual active-core count and which core determines the
model result. Trace each partition through the new prepared map constructor.

Ordering by linear workgroup ID and filling modeled occupancy waves would be
an explicit deterministic assumption, not reconstructed scheduling. SR17 slots
must retain a declared assumption and not be labeled observed. Derive sharing
samples from different supplied core partitions; use the exact global segment
union when tracing all workgroups, or clearly label a sampled estimate. Report
any first/last extrapolation. Do not reuse the current sampled footprint formula
under a claim of exact map replay.

Meaningful host-only gates: a deliberately interleaved map with
core-dependent addresses (waves must never combine distinct cores), a launch
using fewer than 38 cores, an uneven histogram, and a less-populated core with
a longer path. Check these against independently enumerated partitions and
per-lane address sets; retain default/scalar regression comparisons. Recorded
geometry kernels then provide real maps and arithmetic oracles. None of these
checks infers frequency or resolves the current 2.67–3.42x timing residual.
No new GPU probe is necessary to implement or validate partition correctness.

Implemented in the subsequent [supplied-map cost path](../novel-results/2026-10-20-observed-core-map-cost/README.md).
It traces every workgroup, retains full atomic byte ranges, partitions all
workgroups by core, and evaluates all waves without extrapolation. Explicit
wave/memory/cache/slot assumptions accompany the output. All 80 maps and
128 default/scalar-peak predictions pass. Texture/image/stack footprints are
explicitly incomplete; their memory-address tracing remains to be added.
The fixed-grid timing gap stays 2.666–3.425x despite complete supplied core
partitions. Do not fit it away or call these inferred waves measured scheduling.
