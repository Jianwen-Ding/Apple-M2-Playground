# Current owner scope

2026-10-20: continue documenting AGX instruction functionality/performance and
aligning the simulator. Focus ordinary numeric, texture and memory behavior.
The owner explicitly excludes function-transfer and execution-counter-boundary
experiments from continued work. Preserve existing results; do not extend or
rerun those experiment families. These are scope restrictions, not instructions
to bypass any platform safeguards.

Use full-program simulation and independent result oracles before hardware.
Prefer established instruction encodings and bounded arithmetic workloads.
Retain watchdog/kernel/memory diagnostics and exact recovery controls. A failed
recovery or blocked probe stops GPU submissions. Commit and push each completed
piece. The deferred performance-simulator PR review remains a later task.

Current next implementation: optional observed M2 core-map replay in functional
simulation, using the existing ordinary arithmetic corpus without new hardware.
See experiments/arithmetic/observed-core-map-replay.md. Preserve default core-zero
and synthetic stress modes, historical model provenance and literal arithmetic/
guard checks. The geometry study adds 72 full-size maps: all 38 IDs are seen,
and aligned eight-workgroup blocks stay within one cluster at the tested 1-D
32/64/128/256-lane sizes, including neighboring grids' partial tails. Do not
generalize to unmeasured shapes or infer concurrency. The 1000 us host delay
does not guarantee timing stability: one cell retains 2.23x trial variation.
Frequency and the throughput gap remain unresolved. Keep small positive values,
independent whole-program gates and bounded serialized hardware submissions.
No function transfers or execution-counter manipulation beyond the standard
harness prefix.
