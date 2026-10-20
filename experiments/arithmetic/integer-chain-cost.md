# Ordinary integer-add dependency and program length

2026-10-20, before hardware. Follow the unresolved dependent-add prediction
gap from the barrier-cost finding using arithmetic alone. Compare 1/2/4/8
interleaved GPR chains at identical total add counts and register allocation.
All seeds and results are small positive integers; the complete programs are
straight-line, with only established move/add/store/wait/termination forms.

Vary total adds 64/256/1024/2048 (and 4096 if needed), allowing program-length
effects to be separated from dependency shape. Each lane stores every chain's
final value to an allocated per-chain plane; output and table guards are
checked in full. Zero-add programs with the same initialization/store layout
are exact pre/post controls. Candidate and control entire programs must first
match independent scalar full-buffer simulation.

Start with 32 lanes, then 32768/131072 only after exact recovery. Timing uses
firmware timestamps, records power state, interleaves shapes and repeats them.
Report distributions and the samples within 5% of each cell's minimum; do not
claim calibrated cycles or change a global latency from one timing slope.
No function-transfer or execution-counter-boundary experiment is included.
The bounded shared harness retains watchdog/kernel/memory diagnostics. A
failed recovery or blocked process prevents further GPU submission.
