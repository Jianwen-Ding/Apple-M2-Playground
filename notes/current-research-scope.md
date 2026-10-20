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

Current next question: repeat identical ordinary arithmetic programs across
allocations and run order to characterize timing-state variability. The
matched immediate-1/3 study retains the eight-chain 3.6x model gap, while
identical one-chain shaders vary by over 2x across trials. Immediate value
alone cannot explain the observed gap. Keep small positive values, full
scalar/simulator gates, and serialized bounded submissions. No function
transfers or execution-counter manipulation beyond the standard harness prefix.
