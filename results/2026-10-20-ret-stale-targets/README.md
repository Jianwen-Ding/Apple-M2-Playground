# Stale-execution divergent RET target evidence

Ninety gzip records preserve exact code/control/input bytes, simulator and
source hashes, decoded boundaries, competing target predictions, full output
buffers, timestamps, watchdog/kernel/memory state, power and recovery. All
270 dispatches completed; pre/post controls pass, zero events, unchanged boot,
recorded AC-online 0. `target_analysis` is the original hardware classification.

`make verify-ret-stale-targets` reconstructs exact bytes and independently
calculates every checkpoint, counter, prefix and guard. It verifies the winner
from the original mask separately from incoming/post-RET counter participation.
Sixty cases distinguish zero-counter selection, 66 updated participation, and
36 both. All 90 direct measured-model replays match full buffers.

`model-replay.json` binds current binary/source hashes and **2,403** original
evidence-file digests. Saved shader/input bytes replay directly without GPU
access or shader regeneration. Every full main/table buffer matches unchanged
simulator c7e50f7. The per-scope verifier uses independent scalar expectations.

[Interpretation and limits](../../novel-results/2026-10-20-ret-stale-targets/README.md).
