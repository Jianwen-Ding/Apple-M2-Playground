# Program length under a controlled host-gap protocol

2026-10-20, before hardware. The preceding gap study produced closely matching
last-quarter medians with 1000 us added between submissions, while some early
quarters remained faster. Use that same native harness, firmware timing,
watchdog, parser, lock and recovery controls to compare straight-line program
lengths. No new instruction encoding or excluded experiment family is needed.

Use positive immediate-1 additions, the same 64 register halves, and 1/8 GPR
chains. All values stay at most 4196. First run the largest program (4096
adds) on 32 lanes with four consecutive submissions for each chain shape.
Only after complete final-buffer and recovery checks, prepare the entire
matrix in simulation: 131072 lanes, workgroups of 128, 64/256/512/768/1024/
1536/2048/4096 additions, 64 submissions per train and 1000 us host sleep.
Run three deterministically interleaved trials for each full-size cell.

Every shader initializes registers and writes output-only table planes.
Check independent scalar expectations against complete control and candidate
simulation, including successive table states, before hardware. Preserve all
repeat timestamps/waits, actual delay configuration, final buffers and guards,
source/binary/launch metadata, kernel/memory/power state and recovery controls.
Intermediate candidate buffers are not captured. Stop further submissions if
a probe remains blocked or recovery fails. There is one GPU worker.

Retain every early and late sample. Compare candidate-time slopes across
lengths and model predictions at explicit launch settings; the single-submit
controls are correctness checks, not matched timing baselines. Program length
also changes total work and duty, so a change in slope alone does not isolate
instruction-cache effects. Actual operating frequency remains unmeasured.

Completed: 50 trains / 3180 dispatches, exact final buffers and 100 controls,
zero faults. All cell late-median spreads are under 2.3%; the timing shortfall
persists over the sampled size range. See the
[finding](../../novel-results/2026-10-20-integer-length-cost/README.md).
