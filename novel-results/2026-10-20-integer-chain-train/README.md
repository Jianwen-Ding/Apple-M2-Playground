# Consecutive arithmetic dispatches retain the timing gap

M2 Max G14C B1, direct DRM, 2026-10-20. Nineteen bounded trains completed
1,194 dispatches with zero fault events. All 19 final candidate buffers and
38 bracketing recovery controls match complete independent scalar oracles.
The harness captures final buffers only; intermediate candidate buffers were
not captured. Every dispatch has a successful wait and valid firmware times.

Following the [isolated chain study](../2026-10-20-integer-chain-cost/README.md),
run 64 consecutive submissions of each ordinary add program in one harness
process. The full matrix uses 131,072 lanes, workgroups of 128, 64 register
halves, 1 or 8 register chains, and 1,024/2,048/4,096 additions of immediate 3.
Each cell has three trials. A four-submit 32-lane pilot preceded the matrix.
Whole probe windows, including controls, do not overlap. AC remained online
and the boot stayed unchanged.

First and last quarters pool 48 samples each per matrix cell. Early/late
median ratios span 0.991–1.022. Consecutive submissions do not produce
the large late-run speed-up needed to explain the model gap. Last-quarter
slopes remain 75.80–80.02 ns per additional shader add across the full grid,
versus model predictions of 21.27–22.19 ns: a 3.42–3.76 ratio. This does not
measure operating frequency or exclude a sustained clock-state difference.
No calibration parameter changed. Every raw sample remains in the analysis.

The existing immediate-add calibration uses immediate 1, while these programs
use immediate 3. A matched comparison of ordinary immediate values and their
encoded forms is a useful next check before attributing the gap to latency,
instruction fetch, scheduling, or frequency. No causal conclusion follows yet.

[Evidence and offline verification](../../results/2026-10-20-integer-chain-train/README.md).
