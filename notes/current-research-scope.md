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

Current next question: instrument ordinary arithmetic shaders with the known
SR20 core-identity read and a separate output plane to check final-dispatch
per-core work distribution against the model's 38-core assumption. Use matched
instrumentation controls and the same 1000 us host-gap protocol. The completed
length study retains 2.58–3.78x adjacent slope residuals over 600–33066-byte
shaders, with late medians agreeing within 2.3% across three trials per cell.
Keep early and late distributions and do not infer actual operating frequency.
Keep small positive values, full scalar/simulator gates and bounded serialized
submissions. No function transfers or execution-counter manipulation beyond
the standard harness prefix.
