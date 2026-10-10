# Vulkan command-timestamp evidence — 2026-10-10

Run records from `scripts/run_agx_timestamps.py`, copied unchanged from
`/scratch/apple-m2-playground/timestamp-runs/`. Each record has per-variant
oracle/guard results, timestamp limits, and per-dispatch samples:
`ts` = [top-of-pipe before, compute before, compute after, bottom-of-pipe after],
`avail`, and `host_ns` (submit + fence wait).

| File | Contents |
| --- | --- |
| `first-small.json`, `first-scaled.json` | First runs: iadd chain 0..100000 (the pre-`--kind` runner; iadd8 encoding) |
| `sweep-iadd8.json`, `sweep-fadd4.json` | 0..100000 in 12 steps, 5 repeats; used for linearity and the fetch model |
| `matrix-<kind>-c<1,4>.json` | 4/6/8-byte instructions × 1 or 4 independent chains at 0/32768/65536 |
| `count-<i>-c<lanes>.json` | fadd4 65536 at 32..19456 lanes, 12 repeats each, in run order |
| `repeat-iadd8-32768.json` | 64 back-to-back dispatches, no clock-state switch observed |
| `verification.json` | Output of `make verify-timestamps` |

Report: [command timestamps](../../experiments/timing/command-timestamps.md).
