# B10 IRIW probe (2026-10-21): the kernel faults on the GPU, not run to a result

`iriw.py` passes agx_run at every size, but on the GPU every run (65,536 lanes fenced and plain, then 4,096 lanes
fenced, after a passing control) completed with both firmware timestamps 0 in ~1.5 ms, i.e. an instruction-level
fault the simulator does not model. Not bisected (each attempt costs a hang-budget entry). Suspects, in order: the
`bfi r22, 0, r22, r26` form (immediate 0 as the insert base), `asr` with a register amount on r20, and the
role-predicated coherent stores. IRIW (multi-copy atomicity) therefore stays open for B10.
