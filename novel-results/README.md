# New hardware findings

- [2026-10-11 Preshader execution model: once per core, one lane, slot 96; device atomic add](2026-10-11-preshader-execution/README.md)
- [2026-10-11 SR17 hardware SIMD-group slot, SR32 pipeline offset, preshader-last rule](2026-10-11-sr17-sr32/README.md)
- [2026-10-10 Device-load latency, overlap and read bandwidth](2026-10-10-agx-load-latency/README.md)
- [2026-10-10 Counted loops, ALU latency/issue rate, core throughput](2026-10-10-agx-loop-alu-timing/README.md)
- [2026-10-10 Command timestamps, fetch-bound code, direct DRM compute](2026-10-10-command-timing-direct-drm/README.md)
- [2026-10-10 SR18 threadgroup memory and SR19 register allocation](2026-10-10-sr-resource-registers/README.md)
- [2026-10-10 SR7 SIMD-group count and SR20 cluster/core encoding](2026-10-10-sr-geometry-core-id/README.md)
- [2026-10-04 SR lane/active-population behavior](2026-10-04-sr-lane-behavior/README.md)
- [2026-10-04 multiply-add immediate addend](2026-10-04-imadd-addend/README.md)
- [2026-10-04 first native instruction edit](2026-10-04-first-agx-instruction/README.md)
- [2026-10-04 GLES elapsed (failed calibration)](2026-10-04-gles-elapsed/README.md)

For each confirmed finding, create a descriptive folder containing a report
based on `templates/finding.md`, the hardware reproducer (or a stable link to
it under `tests/`), exact inputs/outputs, and relevant environment evidence.
Document which device and software versions were tested and any uncertainty.
