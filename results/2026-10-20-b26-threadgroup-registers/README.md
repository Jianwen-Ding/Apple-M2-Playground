# B26: threadgroup size versus register count, and the 256-half encoding (2026-10-20)

Blocker B26 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: ZLUDA's rule holds and is needed.**
One threadgroup must fit safe-11's per-core budget min(96, 2 floor(3328 / (2 H))) SIMD groups: at 104 halves 1,024
threads run; at 112 halves (budget 28 groups) a 1,024-thread threadgroup that reaches a barrier **hangs** until the
firmware kills it. A Registers field of 0 means 256 halves.

`b26.py`: one threadgroup; every thread writes gid ^ 0x3c3c0000 into its highest declared register
(r(H/2 - 1)), optionally passes a threadgroup barrier, and copies it to the output. Each ran in `agx_run` first.

| Threads | Halves H | Barrier | Budget (groups) | GPU result |
| --- | --- | --- | --- | --- |
| 1,024 | 104 | no / yes | 32 | correct (0 wrong of 1,024, r51), 7.6-8.3 us |
| 384 | 256 (field 0) | no | 12 | correct, r127 of every thread, 8.1 us: **0 encodes 256 halves** |
| 1,024 | 112 | no | 28 | correct, 7.9 us: without a barrier the 32 groups need not be resident together |
| 1,024 | 112 | **yes** | 28 | **hang**: `fw_ts` [0, 0], killed after 0.50 s; the fence still reported success (B20); a control right after passed |

The hang cost one recovery (recorded twice in the hang budget: 5/30 after this run).

For the runtime and backend: refuse launches where one threadgroup exceeds the register budget (ZLUDA's current
`CUDA_ERROR_LAUNCH_OUT_OF_RESOURCES`), and spill to honour `.maxntid` / `.reqntid`. A kernel without barriers would
appear to work over budget, so a missing check would only show up as hangs in kernels that synchronise.

Side observation for B6: a hung command was ended by the firmware after ~0.50 s (the same ~502 ms signature as the
2026-10-11 helper and opcode hangs).
