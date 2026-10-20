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

Current next implementation: carry the optional observed M2 core-map context
into prepared functional tracing, then assess cost-path integration carefully.
Functional execution now supports --m2-core-map / run_with_m2_core_map: all 80
retained maps replay literal complete hardware buffers, with 64 default cases
matching the archived model and independent oracles. Preserve default core-zero
and synthetic stress modes and separate historical/current model provenance.
Do not present supplied state as a placement or timing predictor. Cost replay
must not mix workgroups assigned to different actual cores and imply they were
one observed schedule; SR17 slots and concurrency remain unmeasured.
The geometry corpus's eight-workgroup cluster rule is scoped to tested 1-D
32/64/128/256-lane sizes. Host delay does not guarantee stable timing, and
frequency/throughput remain unresolved. The archived recorded checker is at
the path in results/2026-10-20-observed-core-map-replay/recorded-model.json.
Keep independent whole-program gates and bounded serialized hardware work.
No function transfers or execution-counter manipulation beyond the standard
harness prefix.
