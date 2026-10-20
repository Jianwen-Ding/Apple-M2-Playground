# Controlled-gap program lengths retain a broad arithmetic timing shortfall

M2 Max G14C B1, direct DRM, AC online, 2026-10-20. **50 trains / 3180
dispatches**, zero faults. All 50 final candidate buffers and 100 bracketing
controls are exact. Intermediate candidate buffers were not captured.

Follow the [controlled-gap study](../2026-10-20-integer-timing-state/README.md)
with the same native binary and a 1000 us added host sleep between completed
submissions. Every program uses positive immediate-1 additions, identical
64-half register allocations and 1 or 8 GPR chains. The largest final value
is 4196. Two 32-lane pilots used the largest code size before the full matrix.
All full-program scalar/simulator gates passed before hardware measurement.

The matrix uses 131072 lanes, workgroups of 128, eight add counts and three
deterministically interleaved trials per cell. Every trial has 64 submissions.
Shader sizes range from 600 to 33066 bytes. All measured host intervals include
at least the configured sleep, all firmware intervals lie inside their DRM
get-time brackets, and whole probe windows are disjoint on one unchanged boot.

The table pools the final 16 samples from each of three trials. Times are
microseconds; the model assumes 1398 MHz, which is not measured frequency.

| Adds | 1 chain hardware | Model | 8 chains hardware | Model |
| --- | --- | --- | --- | --- |
| 64 | 15.875 | 8.300 | 27.500 | 9.829 |
| 256 | 28.542 | 11.674 | 39.625 | 13.572 |
| 512 | 45.917 | 17.378 | 56.417 | 18.632 |
| 768 | 63.042 | 23.038 | 73.000 | 24.008 |
| 1024 | 80.334 | 28.680 | 88.375 | 29.959 |
| 1536 | 117.896 | 40.080 | 129.104 | 40.748 |
| 2048 | 156.480 | 51.404 | 168.417 | 51.743 |
| 4096 | 320.917 | 96.850 | 327.834 | 95.531 |

Each cell's three last-quarter medians agree within 2.28%. Keep the early
samples: for one chain / 4096 adds the pooled first-quarter median is 308.833
us versus 320.917 us late. This protocol reduces the large between-trial
variation seen earlier but does not establish invariant timing throughout a
train or across all power/history conditions.

Adjacent candidate slopes, in ns per extra shader add executed by the full
grid, remain substantially above model predictions:

| Add interval | 1 chain hardware | Model | 8 chains hardware | Model |
| --- | --- | --- | --- | --- |
| 64→256 | 65.97 | 17.57 | 63.15 | 19.50 |
| 256→512 | 67.87 | 22.28 | 65.59 | 19.77 |
| 512→768 | 66.89 | 22.11 | 64.78 | 21.00 |
| 768→1024 | 67.55 | 22.04 | 60.06 | 23.24 |
| 1024→1536 | 73.36 | 22.27 | 79.55 | 21.07 |
| 1536→2048 | 75.36 | 22.12 | 76.78 | 21.47 |
| 2048→4096 | 80.29 | 22.19 | 77.84 | 21.38 |

The sampled curve has no large isolated jump and does not identify an
instruction-cache threshold. Both chain shapes retain the shortfall across
the tested range; adjacent slope ratios span 2.58–3.78. This is not a new
instruction latency. Program length changes total work and GPU duty, while
operating frequency, instruction-fetch effects and scheduling are not
independently isolated. Single-dispatch controls are exact correctness checks,
not matched timing baselines; these slopes use candidate durations only.

The model assumes 38 cores. These particular shaders do not record core
identity, so the next check is an established SR20 read plus a separate output
plane to measure final-dispatch per-core work distribution, with matched
instrumentation controls. Verify that assumption before assigning the whole
residual to instruction cost. No simulator timing parameter changed here.

[Evidence and offline verification](../../results/2026-10-20-integer-length-cost/README.md).

The [core-distribution follow-up](../2026-10-20-integer-core-distribution/README.md)
observes all 38 core IDs and a busiest-core tail of 28–33 workgroups versus
the default estimate of 27. A measured-peak model input quantifies that
sensitivity while retaining the remaining timing gap.
