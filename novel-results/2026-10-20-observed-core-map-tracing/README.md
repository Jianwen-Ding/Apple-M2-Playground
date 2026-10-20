# Prepared traces preserve supplied core identities and fresh memory state

2026-10-20, host-only simulator extension. `PreparedDispatch::with_m2_core_map`
now borrows an immutable observed M2 Max core map alongside its dispatch.
`trace_workgroups_with_m2_core_map` offers the same behavior without retaining
a prepared object. The entire map is validated before allocating the decode
cache; all requested workgroup coordinates are checked before parallel work.
Only decoded instruction metadata is shared. Each requested workgroup gets
its own register state and copy-on-write snapshot of caller memory.

The validation checks **69,624 SIMD traces** using all **80 recorded SR20 maps**, including 72 full-size maps
and eight pilots. A new shader makes its store address depend on both core ID
and a stride loaded from memory. Reusing one prepared instance across strides
N and 2N produces independently calculated addresses in both cases. Tests
cover representatives of every observed core, block boundaries, tails,
reordered requests and duplicates. Default prepared traces and freshly
prepared mapped traces are checked against the same per-lane address oracle.
Caller memory stays unchanged. These are new host-only fixture traces using
recorded maps, not additional hardware observations of that fixture shader.

Five targeted library tests pass, including validation before tracing,
existing literal lane/slot checks and default/synthetic behavior. The complete
execution replay also rechecks the 80 observed full buffers and 64 historical
default cases; timing calibration is unchanged.

The supplied map describes core identity only. SR17 slots keep the selected
existing behavior; workgroups trace independently. This is not a concurrent
schedule or a timing replay. The subsequent
[cost-path extension](../2026-10-20-observed-core-map-cost/README.md) partitions
workgroups by supplied core while reporting its wave and memory assumptions.
Slots, overlap and memory interference remain unmeasured.

[Evidence, implementation fixture and reproduction commands](../../results/2026-10-20-observed-core-map-tracing/README.md).
