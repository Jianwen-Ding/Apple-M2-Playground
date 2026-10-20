# Immediate-add comparison exposes repeat-to-repeat timing states

M2 Max G14C B1, direct DRM, 2026-10-20. **26 trains / 1,596 dispatches**
completed without faults. All 26 final candidate buffers and 52 bracketing
controls are exact. Intermediate candidate buffers were not captured.

The preceding studies used immediate 3 while the instruction calibration uses
1. Both forms are eight-byte `iadd` instructions: `0e29541200000000` versus
`0e29543200000000` for r10. Only the immediate field differs. Complete programs
use identical lengths, registers, launches and instruction counts. Immediate-3
programs are byte-identical to the preceding chain study.

After two four-submit 32-lane pilots, compare 131,072 lanes, workgroups of 128,
64 register halves, 1/8 chains and 1024/2048 adds. Each cell has three
deterministically interleaved trials of 64 consecutive submissions. All full
scalar/simulator gates passed before the serial hardware matrix. Every probe
window, including recovery controls, is disjoint. AC was online throughout
on the same boot. These conditions do not measure actual operating frequency.

The table retains each trial's last-quarter median in microseconds:

| Chains | Adds | Immediate | Trial 0 | Trial 1 | Trial 2 |
| --- | --- | --- | --- | --- | --- |
| 1 | 1024 | 1 | 77.604 | 37.688 | 76.709 |
| 1 | 1024 | 3 | 37.542 | 43.646 | 44.729 |
| 1 | 2048 | 1 | 156.313 | 152.709 | 111.563 |
| 1 | 2048 | 3 | 154.771 | 160.604 | 71.188 |
| 8 | 1024 | 1 | 86.126 | 88.105 | 87.875 |
| 8 | 1024 | 3 | 87.042 | 87.271 | 88.250 |
| 8 | 2048 | 1 | 166.396 | 167.313 | 167.416 |
| 8 | 2048 | 3 | 167.521 | 167.375 | 168.480 |

For eight chains the pooled last-quarter immediate-3/immediate-1 ratios are
1.0029 and 1.0061. Its incremental slopes remain 77.17 and 77.92 ns per extra
shader add across the full grid, versus a 21.27 ns prediction: 3.63–3.66x.
The immediate value does not explain this retained eight-chain gap.

For one chain, identical shader bytes and inputs produce substantially
different timings between trials: immediate-1/1024 varies by 2.06x and
immediate-3/2048 by 2.26x. Within some trains the change is already visible
between quarters. Immediate-3/1024 is consistently faster in this batch than
the earlier consecutive-dispatch batch, despite identical shader bytes.
Pooling these mixed states cannot establish an immediate-specific latency.
The analysis retains descriptive pooled slopes, every sample, trial ratios
and chronological probe ordering; they are not causal calibration estimates.

The next check should repeat identical programs across allocations and run
order, retaining the timing states and launch provenance. Clock state,
instruction-fetch/cache behavior and scheduling remain hypotheses. No global
simulator cost changed; the current model predicts equal cost for both values
and does not reproduce these variable hardware timing states.

[Evidence and offline verifier](../../results/2026-10-20-integer-immediate-cost/README.md).
