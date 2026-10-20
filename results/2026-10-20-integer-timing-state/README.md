# Controlled host-gap arithmetic evidence

Thirty-nine gzip records retain exact code and control bytes, complete input
and final buffers, guards, native configuration/stdout, every repeat index,
wait result, firmware timestamp, get-time bracket and host wait duration,
source/binary hashes, launch descriptors, kernel/memory/power snapshots and
recovery controls. All 2316 timed candidate submits and 78 controls complete;
all final buffers are exact. Intermediate candidate buffers are not captured.

`make verify-integer-timing-state` performs no GPU work. It gates each unique
complete shader against independent full-buffer arithmetic expectations,
including successive table states. It checks every control and final train
buffer, completion marker, device parameter record, repeat index and wait.
Every firmware interval must lie inside its corresponding DRM get-time
bracket; whole probe windows must be disjoint on one boot with AC online and
zero fault events. Every observed host interval must include at least the
configured sleep. Native stdout must report the same delay as its gate.

The verifier also checks native/source/functional/model/calibration bindings
and the exact [native-source diff](native-origin.patch). The native source
is [drm_integer_timing.c](../../experiments/arithmetic/drm_integer_timing.c).
Invalid host delays above 10000 us or negative values are checked to fail
before device access, using `/dev/null` arguments. The common harness remains
unchanged, preserving earlier evidence bindings.

`analysis.json` retains record digests, chronological probe order, every
firmware sample, preceding firmware idle interval, host interval, host wait
and DRM bracket duration, quarter medians and candidate train-window duty
fractions. It also reports per-cell trial ranges and exact model settings.
The native binary is rebuilt in scratch if missing; source and binary hashes
are pinned. The 1398 MHz prediction is an assumption, not measured frequency.

[Interpretation and limits](../../novel-results/2026-10-20-integer-timing-state/README.md).
