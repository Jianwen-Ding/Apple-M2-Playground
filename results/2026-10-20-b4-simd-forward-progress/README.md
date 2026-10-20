# B4: forward progress inside a SIMD group (2026-10-20)

Blocker B4 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: never.** A divergent SIMD group runs
the `if` side of an if/else to completion before the `else` side, whatever the lane counts. Lanes spinning in the
`if` side on a value that lanes of the same group write in the `else` side never see it, so such a spin deadlocks.

`b4.py` (uses the simulator's `record_suite` / `coverage` helpers): spinners run a loop of exactly N trips (Mesa's
structured-loop form from `agx_loop.loop_body`: push_exec, body, `while_icmp`, `jmp_exec_any`, pop_exec) that loads
the flag (table word 0, initially 0) from device memory and records the first trip on which it is nonzero
(0xffffffff = never). Writers in the other branch store 1 to the flag. The loop never exits early, so the program
ends whatever the scheduling. Each program ran in `agx_run` first (same results), then once on the GPU; 0 faults.

| Variant | `if` side (runs first) | `else` side | N | Spinner saw the flag at trip | Flag after | Firmware time |
| --- | --- | --- | --- | --- | --- | --- |
| `spin_if_lane0` | lane 0 spins | lanes 1-31 write | 2,000 / 200,000 | **never** / **never** | 1 | 0.40 / 15.9 ms |
| `spin_if_lanes1_31` | lanes 1-31 spin | lane 0 writes | 2,000 / 200,000 | **never** / **never** | 1 | 0.41 / 16.6 ms |
| `spin_else_lane0` | lanes 1-31 write | lane 0 spins | 2,000 / 200,000 | 0 / 0 | 1 | 0.41 / 18.0 ms |

The writes do land (flag = 1 afterwards), but only after the `if` side has finished all its trips.

**For ZLUDA / the backend:** PTX code that relies on independent thread scheduling (`sm_70+`) inside a warp, for
example a lock held by one lane while another lane of the same warp spins, will hang. Either rewrite such patterns
(put the critical section inside the lock loop, as the backend already does for its own emulated wide atomics) or
report pre-Volta scheduling semantics.

Not covered: threadgroup-memory flags (the scheduling order, not the memory path, decides the result here), and
whether any other construct (e.g. a barrier or `wait` inside the loop) yields to the other side.
