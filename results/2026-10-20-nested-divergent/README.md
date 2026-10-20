# Nested three-target inner-call evidence

Twelve compressed records: direct/indirect outer calls, inner winner A/B/C,
seeds 17/257. Each is surrounded by exact no-call/no-return conditional
controls: 36 dispatches, zero faults. Full code/input/readbacks, source/harness
hashes, all-target simulator gates, decoded boundaries, firmware samples and
watchdog/kernel/memory/recovery metadata are preserved unchanged.

The table holds 32 initialized inner targets; subsequent 32-word planes are
prefix, outer link/marker, inner link/identity, r0 before inner pop and after
pops 1/2, reconverged inner r1 and saved outer r29, final continuation and
outer r1, outer pop-1/fallback diagnostic, then 16 guards. Main output stays
untouched. Every initial target is valid and all three are present.

`make verify-nested-divergent` reconstructs exact programs, checks provenance
and link formulas independently, and checks every output word against scalar
participation and payload sets. No GPU is used by the verifier. See the
[finding](../../novel-results/2026-10-20-nested-divergent/README.md).
