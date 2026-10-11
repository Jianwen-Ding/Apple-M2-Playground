# New hardware findings

- [2026-10-11 0x78 = barrier over aligned 4-SIMD-group blocks, 0x68 = whole workgroup; usable threadgroup memory = declared/4](2026-10-11-barrier-0x68-vs-0x78/README.md)
- [2026-10-11 0x78 (4-SIMD-group) barrier, 0x18 fixed-cost op, ending opcodes indistinguishable; threadgroup memory on direct DRM](2026-10-11-sync-and-end-opcodes/README.md)
- [2026-10-11 Undecoded-opcode descriptions: 6-byte no-ops, 0x18/0x78 control ops, mask-independent SIMD-group end; under-declared registers corrupt](2026-10-11-opcode-descriptions/README.md)
- [2026-10-11 SR12/SR13 imageblock dimensions, SR15 sample stride](2026-10-11-sr12-sr13-sr15-imageblock/README.md)
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
