# Three-target transfer corpus

72 records: call/ret × first-active 0,1,5,8,16,24 × winner A/B/C × seeds 103/809.
Every record has all three target addresses represented in active lanes, an
inactive hole immediately above the lowest active lane, and exact program,
input, surrogate, readback, provenance, kernel/firmware/memory and recovery data.

Eight 32-word planes plus 16 guards: targets, active bits, prefix marker,
first landing marker, entry-time link (call) or post-pop-2 marker (return),
post-pop marker (call only), fallback marker, and post-pop r1. The separate
main output is fully guarded and untouched. Caller/callee addresses use the
same buffer-relative byte convention as the parent findings.

`make verify-three-targets` regenerates and fully simulates each actual program,
all six surrogate paths and then independently checks every hardware word and
device identity. It requires the adjacent release `agx_run` / `agx_asm` binaries
and uses no GPU. Hardware runs used the shared watchdog and the adjacent
simulator's native direct-DRM C harness. [Finding](../../novel-results/2026-10-20-three-targets/README.md).
