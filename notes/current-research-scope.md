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

Current next question: vary workgroup geometry with matched SR19/SR20 output
planes and the 1000 us host-gap protocol. All 12 full-size arithmetic core maps
contain all 38 IDs, but the busiest core receives 28–33 workgroups versus the
default estimate of 27. Cluster totals are multiples of eight at the tested
128-lane / 1024-workgroup geometry; test other shapes before generalizing.
The simulator now accepts an explicit measured peak as a sensitivity input;
it leaves a 2.76–3.06x final-dispatch timing residual and does not reconstruct
the actual placement map or concurrency. Keep early and late distributions,
exact arithmetic/guards and complete core-map property checks. Frequency is
unmeasured. Keep small positive values and bounded serialized submissions.
No function transfers or execution-counter manipulation beyond the standard
harness prefix.
