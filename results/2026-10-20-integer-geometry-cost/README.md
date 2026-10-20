# Workgroup-geometry and cluster-block evidence

One hundred sixty gzip records retain exact shaders, controls, input and
complete final buffers, tag planes and guards, native delay/stdout, every
repetition/wait/completion marker and firmware/get-time timestamp, launch/
source/binary hashes, kernel/memory/power snapshots and recovery controls.
There are 9280 candidate submissions and 320 controls, with zero fault events.
Physical core maps use complete property checks, not default-placement literal
expectations. Intermediate buffers are not captured.

`make verify-integer-geometry-cost` performs no GPU work. It rebuilds every
unique full-program/launch pair and checks scalar/default-placement simulation,
successive table states, all arithmetic and guards, literal SR19 allocation
tags and every SR20 tag's mask and workgroup uniformity. It verifies actual
delay, device parameters, every repetition and timestamp bracket, observed
host intervals and nonoverlapping whole probe windows on one boot.

`analysis.json` binds every record, model/source/calibration version and the
preceding core-distribution analysis. The native source and binary are unchanged.
It retains chronological ordering, every timing sample, per-trial quarters,
complete core/cluster histograms, matched-tag ratios, default predictions and
measured-peak sensitivity for the corresponding final dispatch. It also tests
aligned block widths 1/2/4/8/16/32/64/128, including incomplete final blocks,
and retains the rejected fixed-thread-count hypothesis's mixed-block counts.
Those patterns were observations, not preconditions on hardware acceptance.

`make test-integer-geometry-cost` independently checks the analysis with a
four-workgroup-block fixture and a partial tail, then changes one workgroup's
cluster to ensure a mixed block is reported rather than forcing a hypothesis.
The existing core-plane corruption suite also passes. All checks are host-only.

The runner only redirects the established core probe's output destinations;
its instruction construction, parser, native code, watchdog, lock and recovery
flow are unchanged. No instruction timing calibration or placement predictor
was changed from these results.

[Interpretation and limits](../../novel-results/2026-10-20-integer-geometry-cost/README.md).
