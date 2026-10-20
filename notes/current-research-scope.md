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

Current next question: separate register dependency from program-length effects
in ordinary integer-add chain timing, following the 2026-10-18 barrier-cost
finding. This uses small positive integer values, no function transfers,
no execution-counter manipulation beyond the standard harness prefix, and
straight-line already measured arithmetic instructions.
