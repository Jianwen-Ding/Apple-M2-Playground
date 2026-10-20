# Consecutive ordinary arithmetic dispatches

2026-10-20, before hardware. Isolated arithmetic timing does not establish
operating frequency. Use the exact established chain programs in one harness
process for 4/16/64 consecutive submits (the existing harness's bounded limit).
There is one GPU worker and no clock-keeping background workload. Register
seeds are initialized on every dispatch and table memory is output-only.
Simulate successive invocations from the preceding table result as well as
the initial full-program/scalar gates.

Preserve every firmware timestamp, wait result and final complete buffer.
The harness captures final buffers only; do not claim intermediate per-dispatch
buffers were independently checked. Exact single-dispatch zero-add controls
bracket the train, with phase-by-phase evidence saved before submission,
bounded watchdogs, kernel/memory/power/boot metadata and recovery controls.
Any blocked process or failed recovery prevents further GPU work.

Start with four repetitions of the 32-lane pilot. Only after exact recovery,
use 131072 lanes and 64 repetitions of the established chain shapes. Compare
first/last-quarter distributions, keeping every sample. Cache, scheduling and
frequency can all affect warm-up; no cycle claim follows without separating
them. No new instruction encoding or excluded experiment family is involved.

Completed: 19 trains / 1,194 dispatches, all final candidate buffers and
bracketing controls exact, zero faults. First/last-quarter timing medians
remain close; the model slope gap persists. See the
[finding](../../novel-results/2026-10-20-integer-chain-train/README.md) and
[retained evidence](../../results/2026-10-20-integer-chain-train/README.md).
