# Timing can change within one arithmetic train; longer host gaps stabilize late samples

M2 Max G14C B1, direct DRM, 2026-10-20, AC online. **39 bounded trains /
2,394 dispatches**, zero faults. All 39 final candidate buffers and 78
bracketing controls are exact. Intermediate candidate buffers were not
captured. Full scalar and simulator gates passed before hardware.

Following the [immediate comparison](../2026-10-20-integer-immediate-cost/README.md),
reuse byte-identical immediate-1 shaders across trials. Each full-size shader
has 1024 additions, 131072 lanes, workgroups of 128 and 64 register halves.
The 1/8-chain shapes each run six interleaved trials at three configured host
delays: 0, 250 and 1000 us between completed submissions. Every trial reuses
the same VM, queue and buffer objects for 64 submissions; the next trial
allocates new objects. Three 32-lane, four-submit pilots preceded the matrix.

The separate native harness differs from the common bounded DRM harness only
by a checked host-delay setting, a configuration print and nanosleep after a
completed submission. It preserves shader and launch bytes, buffer cleanup,
the three-second wait and the 64-submit limit. The host process watchdog is
ten seconds. The native harness confirms its setting in stdout; all measured
inter-submission get-time intervals are at least the configured delay.

Each row summarizes six last-quarter medians, in microseconds. The delay is
additional host sleep, not the complete idle interval.

| Chains | Added host delay (us) | Median of trial medians | Minimum | Maximum |
| --- | --- | --- | --- | --- |
| 1 | 0 | 76.875 | 44.417 | 77.167 |
| 1 | 250 | 77.313 | 76.917 | 78.709 |
| 1 | 1000 | 80.334 | 80.021 | 80.855 |
| 8 | 0 | 86.708 | 86.063 | 88.125 |
| 8 | 250 | 88.146 | 77.500 | 88.459 |
| 8 | 1000 | 88.490 | 88.354 | 88.667 |

With 1000 us added sleep, the six late medians vary by 1.0104x for one chain
and 1.0035x for eight chains. This gives a reproducible late timing regime in
this batch, rather than the fastest regime. Median measured host intervals
are 1182.7/1201.0 us, and the candidate's measured train-window duty fractions
are about 4.9/5.1%. The current 1398 MHz model predicts total durations of
28.680/29.959 us. This experiment has one add count, so it establishes no new
incremental slope or instruction latency.

**Allocation alone cannot explain the timing states.** One-chain trial 5
with the 1000 us setting has quarter medians 47.604, 59.854, 80.771 and
80.146 us within one process using the same objects and shader bytes.
Eight-chain trial 3 at the same setting changes from 66.271 to 88.459 us
between first and last quarters. Thus even the more stable late regime can
begin in a faster state. Allocation may still contribute; this rules out a
fixed per-allocation cost as the sole explanation.

Current operating frequency is unmeasured: devfreq exposes no devices and
DRM debugfs is unavailable in this environment. Delay/history, frequency,
instruction fetch/cache and scheduling remain possible contributors. Host
delay is controlled here; the other variables are not independently isolated.
No cost-model parameter changed and the model does not reproduce these
within-train timing transitions.

Next, compare ordinary program lengths under the same 1000 us host-delay
protocol, retaining early and late distributions. This can test how much
length-dependent residual remains in a more reproducible timing regime.

[Evidence, native-source diff and offline verifier](../../results/2026-10-20-integer-timing-state/README.md).

The [program-length follow-up](../2026-10-20-integer-length-cost/README.md)
retains the shortfall over 600–33066-byte shaders, with last-quarter medians
agreeing within 2.3% across three trials per cell under the 1000 us protocol.
