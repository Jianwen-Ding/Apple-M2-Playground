# Arithmetic workgroup geometry and cluster packets

2026-10-20, before hardware. The preceding core maps show all 38 cores, with
28–33 workgroups on the busiest core. Host-only analysis of those 12 final
maps also shows that every aligned block of eight consecutive 128-lane
workgroups stays in one cluster. Do not generalize that fixed-geometry
observation without testing other sizes and partial final blocks.

Reuse the established arithmetic, SR19/SR20 twins, complete-buffer checker,
native 1000 us host-delay harness, parser, watchdog, GPU lock and recovery
flow. Only output destinations and launch geometry change. Values remain
small positive integers, allocation stays 64 halves, and twins differ only
in the selector of one get_sr instruction. No new instruction forms are used.

First run one workgroup of 32/64/128/256 lanes, 4096 adds and four submissions
for each 1/8-chain and SR19/SR20 combination (16 pilots). After exact controls
and all buffer/property checks, gate the complete full matrix before timing:
131072 lanes at each of those workgroup sizes, plus 130944 and 131200 lanes
at size 128 (1023/1025 workgroups). Cross all six geometries with 1/8 chains,
1024/4096 adds and both selectors, then run three deterministically interleaved
trials of 64 submissions (144 full-size trains).

Independent scalar expectations cover arithmetic, guards and SR19 tags. SR20
simulation must match default-placement zeros, while physical maps are checked
for enabled IDs, workgroup uniformity and complete coverage, never a forced
equal distribution. Simulate successive table states. Preserve all timestamps,
actual native delay, final buffers, source/binary/launch bindings and kernel/
memory/power/recovery diagnostics. Intermediate maps and concurrent residency
are not measured. Failed recovery or a blocked process stops GPU submissions.

Analyze aligned cluster-packet widths and partial tails as observations, not
oracle constraints. Compare timings, peaks and measured-peak model sensitivity
across geometries. Operating frequency remains unmeasured; no default timing
recalibration follows merely from the remaining residuals.

Completed: 160 trains / 9600 dispatches, exact arithmetic/guards and all 320
controls, valid complete SR20 maps, zero faults. All 72 full-size maps preserve
aligned eight-workgroup cluster blocks across the tested shapes and partial
tails. The fixed-thread-count hypothesis is rejected, and one neighboring-grid
cell retains 2.23x trial timing variation despite the host delay. See the
[finding](../../novel-results/2026-10-20-integer-geometry-cost/README.md).
