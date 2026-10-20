# Consecutive return-counter evidence through 31

Sixteen compressed records: maxima 5/7/15/31, rotations 0/1, original-state
jump/RET. Exact payload-only controls before and after yield 48 dispatches,
zero faults. Original/return maxima were checked stepwise before rotation.

The 4,240-word masked-r0 layout is unchanged: original/desired inputs, prefix,
two full 32-source low-r0/payload gathers, final marker and guards. Only the
bounded post-snapshot drain grows; every target/gather address stays fixed.
All inputs are initialized before divergence; upper r0 bits are masked away.
Exact code/input/readbacks, source/harness hashes, current deeper-counter
gates, boundaries, firmware samples and diagnostics/recovery metadata remain
preserved. Run `make verify-deep-ret-counters` for exact reconstruction,
provenance and independent full-buffer checks. See the
[finding](../../novel-results/2026-10-20-deep-ret-counters/README.md).
