# Independent add chains retain the isolated-dispatch timing shortfall

M2 Max G14C B1, direct DRM, 2026-10-20. **83 programs / 249 dispatches**:
every arithmetic result, output guard and recovery control exact; zero faults.
AC-online is 1 throughout, with one unchanged boot.

Following the earlier barrier-cost finding, compare 1/2/4/8 interleaved GPR
chains at identical total add counts. The same 64 register halves are allocated
for every shape. Values remain small positive integers. Every lane stores
each chain's final value, and the whole candidate/control programs first pass
complete-buffer simulation and an independent scalar oracle. Programs are
straight-line sequences of previously measured ordinary arithmetic forms.

Three small pilot programs preceded the timing matrix. The matrix has
131,072 lanes, workgroups of 128, 64/256/1024/2048 total additions, four chain
counts and five deterministically interleaved repetitions per cell. Every
sample is retained; each cell's fast cluster is within 5% of its minimum.
The table shows candidate-time slopes, in ns per additional shader add
executed by the full 131,072-lane dispatch:

| Chains | Hardware, 256→1024 adds | Model | Hardware, 1024→2048 adds | Model |
| --- | --- | --- | --- | --- |
| 1 | 68.20 | 22.14 | 81.58 | 22.19 |
| 2 | 64.94 | 21.45 | 74.16 | 21.47 |
| 4 | 66.24 | 21.55 | 74.06 | 21.33 |
| 8 | 64.67 | 21.34 | 75.89 | 21.27 |

Interleaving does not remove the shortfall: these isolated-dispatch incremental
ratios are 3.03–3.68 across all shapes. This weakens the earlier attribution to
single-register dependency alone. It does **not** establish a new instruction
latency. Program length, instruction fetch, scheduling and clock/warm-up state
remain separate explanations; the comparison model assumes 1398 MHz, while
the operating clock during these short dispatches was not measured.

Pre/post zero-add controls verify complete-buffer correctness. Their timing
is not a reliable matched launch baseline: subtracting their average can give
negative short-program increments because their positions in the run differ.
The reported slopes therefore use only candidate fast-cluster medians at
different add counts. Raw sample distributions, control times, cluster sizes,
program lengths and model predictions remain in `analysis.json`.

No global latency or throughput parameter was changed from this experiment.
Next, run bounded consecutive repetitions of the same ordinary arithmetic
program in one harness process, without another GPU worker. That can separate
warm-up from the isolated-dispatch observation before calibration changes.
No function-transfer or execution-counter-boundary experiments are involved.

[Evidence and offline verification](../../results/2026-10-20-integer-chain-cost/README.md).

The [consecutive-dispatch follow-up](../2026-10-20-integer-chain-train/README.md)
is complete: no large late-run speed-up, with the timing gap retained.
