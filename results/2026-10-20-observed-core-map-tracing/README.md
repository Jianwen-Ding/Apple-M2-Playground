# Prepared functional tracing with supplied M2 core maps

Host-only verification, 2026-10-20. No GPU submissions or new hardware timing.

Reproduce from the playground with the sibling simulator checkout available:

```
python3 -B scripts/verify_observed_core_map_tracing.py --result /tmp/core-map-tracing.json
python3 -B scripts/verify_observed_core_map_replay.py --result /tmp/core-map-execution.json
```

The tracing verifier checks all 160 raw geometry records and their 320 controls
against independent arithmetic/tag/guard oracles and their canonical SHA256s.
It extracts all 80 SR20 maps, then builds the retained Rust host-only driver
in `experiments/arithmetic/core-map-traces`. Cargo dependencies are locked;
build products are stored under `/scratch/apple-m2-playground`.

For each supplied map it traces representatives of every distinct core plus
aligned-block boundaries, final workgroups and duplicate/reordered requests.
The nine-instruction shader reads global X and SR20, loads a stride from
memory, computes `core * stride + global_x`, and stores the core ID through
that index. Two input memory snapshots use strides N and 2N with the same
prepared object. A separate per-lane integer formula checks every 64-byte
load/store segment, instruction offset, SIMD-group count, warning and skip.
The default prepared path and a freshly prepared mapped path receive the
same checks. Caller memory must remain untouched, including all output
planes and the stride input. Four CPU tracing workers are used; these are
not GPU workers.

`analysis.json` records the shader bytes, instruction offsets, selected
workgroups, a total of **69,624 SIMD traces**, and source/input/binary hashes.
The separate
`execution-regression.json` repeats the existing 80 literal full-buffer
replays, 64 archived/current default comparisons and five invalid-map CLI
checks using the newly built functional binary. Historical measurements and
canonical reports are preserved.

This replays supplied core identities into isolated functional traces. It
neither reconstructs SR17 slots nor measures concurrent residency, memory
interference, operating frequency or dispatch timing. The later [cost-path extension](../2026-10-20-observed-core-map-cost/README.md)
accepts complete maps with explicit wave/memory assumptions; the scalar
busiest-core input remains a separate approximation.
