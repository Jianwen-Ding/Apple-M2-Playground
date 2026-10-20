# Exhaustive cost modeling over supplied core partitions

2026-10-20, host-only. Reproduce after building the sibling simulator's
`agx_dispatch` release binary:

```
python3 -B scripts/verify_observed_core_map_cost.py --result /tmp/core-map-cost.json
```

`analysis.json` retains per-core/per-wave predictions and independent checks
for every supplied geometry map. The verifier rechecks all 160 raw records and
320 controls against their hashes, regenerated shader bytes and independent
arithmetic/tag/guard expectations. All 80 SR20 maps are evaluated through the
CLI. Independent Python enumeration checks actual core membership, workgroup
order, occupancy-sized chunks, complete coverage without duplicates, the
critical core and completion/launch formulas. The known store-only shaders
have disjoint chain/tag planes, so their exact global footprint is
`N * (chains+1) / 16` 64-byte segments with zero cross-core sharing.

A separate core-dependent address fixture checks an intentionally interleaved
80-workgroup map using two cores (60 versus 20 workgroups), a shared stride
load, and disjoint store lines. Its global footprint is 161 segments. Every
wave's sharing is independently `1 / (2*wave_workgroups + 1)`. The shader bytes
come from the preceding retained functional-trace fixture; this is not a new
hardware observation of that program.

The verifier compares all 64 unique ordinary program/launch cases in both
legacy default and scalar-peak modes: 128 predictions must match the archived
binary's complete JSON exactly. The archived dispatch SHA256 is
`6c7b860e32e6734102cd77147cd58f37cbbe1fb8788313ad366a37f4452a0720`, kept under
`/scratch/apple-m2-playground/model-versions/<sha256>/agx_dispatch`.
Historical model/data provenance is not rewritten. The report pins the current
binary, every Rust source file, Cargo manifests/lockfile and cost parameters.

Eight invalid CLI cases check rejection before missing shaders, preambles or
buffers are accessed. A three-job batch checks result order and per-job error
isolation. `dispatch-tests.txt` and `cli-unit-tests.txt` retain the relevant
library and CLI test output. `memory-trace-tests.txt` additionally retains
the 960-case independent byte-range oracle and legacy memory-trace regressions.
`functional-core-map-tests.txt` preserves the five functional core-map tests,
including default/synthetic slot values and prepared snapshot reuse.
`trace-regression.json` rechecks 69,624 ordinary load/store traces across all 80
recorded maps and two memory snapshots, including the new device footprint
field. `execution-regression.json` rechecks all 80 literal hardware buffers
and 64 unchanged archived/current default executions after rebuilding.

Timing comparisons pair each final hardware dispatch's time with the map read
back from that dispatch. The current frequency, launch, occupancy and issue
constants remain unchanged. Linear per-core wave order, isolated memory
snapshots, cold per-wave cache state, footprint-based SLC residency and
simultaneous-core completion estimates are assumptions. Actual slots,
concurrent residency, clock state and inter-core overlap remain unmeasured.
The model must not be described as a measured schedule or a calibrated timing
replay. No GPU dispatches or recovery actions occur in this verifier.

Additional host-only commands:

```
python3 -B scripts/summarize_observed_core_map_cost.py --result /tmp/core-map-timing.json
python3 -B scripts/inspect_gpu_clock_interfaces.py --result /tmp/gpu-clock-interfaces.json
```

`timing-comparison.json` pairs all 72 full-size supplied-map estimates with
canonical scalar measured-peak estimates using the exact final timestamp and
core histogram. On the 48 fixed-N maps the supplied/peak estimate range is
0.9999999999999998–1.00326736255709, median 1.0. Hardware/supplied estimates
remain 2.666235040539957–3.4247225336055003, median 2.9542378718330156.
`clock-interfaces.json` preserves a read-only interface inventory: devfreq is
empty, DRI/Asahi debugfs and Asahi module parameters are absent here, and GPU
runtime-PM status says unsupported. The autosuspend attribute returns an I/O
error; this is a sysfs read result, not a failed GPU submission or recovery.
No frequency value is measured by this inventory.
