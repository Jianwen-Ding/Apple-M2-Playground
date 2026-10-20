# Cost estimates now preserve supplied core partitions

2026-10-20, host-only simulator extension. `agx_dispatch --m2-core-map FILE`
and the library's `mapped_dispatch::simulate` now consume the same validated
M2 Max core identities used by functional execution and prepared tracing.
They trace every workgroup and partition it by its supplied core before
assembling any modeled wave. Each workgroup appears exactly once. The number
of active cores comes from the map; the critical core is selected from its
modeled completion time, not from the largest workgroup count alone.

The output includes every core's workgroups, all modeled waves and their
cycles/sharing, the critical core, and explicit assumptions. Waves follow
linear workgroup order within each core and the existing occupancy model;
none are extrapolated. Each workgroup starts from its own memory snapshot.
SR17 uses the selected dispatch placement mode (the CLI uses group index
within the workgroup). Neither slots nor overlap were measured by the maps.
The estimate takes the maximum per-core completion time plus fixed dispatch
overhead; actual inter-core start times and overlap remain unknown.

The global device footprint is the union of segments from every isolated
trace. Functional traces retain device load/store segments and the complete byte
range of each atomic separately from legacy cost word addresses. This covers
32/64-bit atomic accesses crossing a 64-byte boundary without losing low address
bits. Wave sharing is averaged against
all other supplied core partitions, avoiding the former representative path's
assumption that selected grid IDs lie on other cores. SLC residency remains
a footprint-based assumption and cache state restarts at each wave.
Texture/image/stack accesses and texture/sampler descriptor reads currently
lack these memory traces: the report
marks the footprint incomplete and does not assume SLC residency for them.
That does not extend texture timing calibration.

Seven new library tests cover interleaved partitions with an uneven histogram,
a partially filled final wave, two active cores instead of 38, a less-populated
but more expensive critical core, exact memory sharing/footprint and atomic
address units and crossing/unaligned byte ranges, 2-D maps, single-core sharing and invalid context before decode.
A further byte-by-byte oracle covers 960 atomic width/alignment/mask cases.
The unaligned cases are host-only model fixtures and establish no hardware
alignment behavior. A descriptor-only fixture also confirms incomplete footprint coverage without
any texel access. The CLI rejects a scalar peak, an explicit wave limit or a non-M2 core count
alongside a full map. Map errors precede shader/preamble reads and buffer
allocation. Batch results preserve job order and isolate a bad map.

The retained geometry verification checks all 80 SR20 maps against independent
partition, wave, footprint and sharing oracles, plus all raw candidate/control
buffers. Legacy default and scalar-peak predictions are compared literally
with the archived dispatch binary. No model constants were fitted, no new
hardware was submitted and no new hardware scheduling facts are claimed.

[Evidence and reproduction](../../results/2026-10-20-observed-core-map-cost/README.md).

On the 48 fixed-N full-size maps, exhaustive partition estimates are
**1.0000–1.0033×** the retained scalar measured-peak estimates (median 1.0000;
the smallest floating-point result is 0.9999999999999998). Final-dispatch
hardware/model ratios remain **2.666–3.425×**, median **2.954×**. The full
72-map comparison is preserved in `timing-comparison.json`. Supplying the
complete core map and eliminating wave extrapolation do not explain the
large residual for these ordinary integer kernels. This does not identify
which unmeasured clock, scheduling or throughput state causes it.

A read-only interface inventory found an empty `/sys/class/devfreq`, no
exposed Asahi/DRI debugfs directories, and unsupported runtime-PM status for
the GPU in this container. These paths provide no measured GPU frequency
here. The inventory made zero DRM ioctls and no submissions; it does not
establish whether another host interface could expose the necessary telemetry.
