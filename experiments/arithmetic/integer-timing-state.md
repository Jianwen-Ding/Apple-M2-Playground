# Identical shaders and controlled host gaps

2026-10-20, before hardware. The immediate comparison found >2x variation
between identical one-chain shaders. Existing records show both fast and slow
runs with similar preceding firmware idle intervals, so an uncontrolled gap
alone does not determine the timing state. Current GPU frequency telemetry is
not exposed by devfreq/debugfs in this environment.

Use unchanged immediate-1 programs and a separate copy of the bounded DRM
harness with one addition: an optional 0–10000 us nanosleep between completed
submissions. Preserve the common harness and its earlier source bindings.
The candidate values are 0, 250 and 1000 us; this is a host delay, not a shader
wait. Read back its configured value from harness stdout. Existing three-second
submit waits, 64-repetition limit and ten-second process watchdog remain.

First run each delay on 32 lanes / 64 adds / four repetitions, with whole
scalar/simulator gates and full final-buffer/recovery checks. After recovery,
prepare all full-program gates before measuring 131072 lanes, workgroups of
128, 64 register halves, 1/8 chains and 1024 adds. Six interleaved trials per
chain/delay, each with 64 submissions. A native process reuses the same objects
throughout its train; each new trial allocates fresh objects and a VM/queue.

Use a single worker under the existing lock. Save exact code/input/final
buffers, repeat/wait/completion metadata, firmware and get-time timestamps,
host timings, source/binary hashes, kernel/memory/power state and bracketing
controls. Intermediate candidate buffers are not captured. A blocked process
or failed recovery stops further submissions. Analyze within-train state and
between-trial variability; no clock or allocation-causality claim follows
from association alone. The model cost stays unchanged without an explanation.

Completed: 39 trains / 2394 dispatches, exact final buffers and 78 controls,
zero faults. A 1000 us host delay gives closely matching late medians across
six trials, but timing still changes within some trains using the same
objects. See the [finding](../../novel-results/2026-10-20-integer-timing-state/README.md).
