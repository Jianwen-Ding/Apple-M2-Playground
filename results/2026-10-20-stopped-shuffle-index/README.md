# Paired immediate/register stopped-source evidence

256 compressed records: four maximum depths, two rotations, all 32 target
indices. Candidate/control differ only at STOP/wait. Each record retains full
code, inputs, readbacks, source/harness hashes, simulator gates, firmware
samples, diagnostics and exact before/after recovery controls. 768 dispatches,
zero faults. The first three diagnostic cases were inspected separately.

Table: 32 original depths, 32 prefix markers, paired 32-word immediate/register
gathers before stop and after pop 1, 32 final markers after four more pops and
16 guards. Uniform index r15 is initialized in all physical lanes before any
mask or stop. Payload r14 holds unique lane IDs. Simulator counterexamples
are intentional and checked: 82 dead-source cases; 174 living-source cases
already match. Original evidence is unchanged.

Run `make verify-stopped-shuffle-index` for exact program reconstruction,
provenance checks, independent full-buffer oracles and simulator gap accounting.
See the [finding](../../novel-results/2026-10-20-stopped-shuffle-index/README.md).
