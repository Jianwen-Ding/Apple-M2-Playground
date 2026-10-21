# B37: checked mode on the hardware (2026-10-21)

Blocker B37 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), battery power. LLVM AGX fork 3736ce1
and ZLUDA master 7a6d979 built locally (`notes/local-patches`); kernels compiled by `zoc --agx-checked` and run through
the fork's `llvm/utils/agx-checked/zluda_tests.py` / `run_checked.py`, with ZLUDA's `agx_run_hw` (agx_run's command line on
the GPU) as `--agx-run`. Every case ran in agx_run first (`zluda_tests-sim-tail.txt`: 0 failures). 0 GPU faults; hang
budget unchanged.

## 1. The same records as the simulator: pass

`zluda_tests-hw.txt`: **all 17 G14C cases pass on the GPU** with the expected kind, address, thread and threadgroup
(off-by-one store at 0x2000080 by thread 32; null store; misaligned load at 0x1000002; threadgroup and dynamic
threadgroup overflows; out-of-bounds atomic; struct-carried pointer; second block; pointer chase past the end; the
inlined `.func` reported as `put put.h:3:7` called from `k inl.cu:12:5`), correct kernels report nothing, and **all 7
controls pass** (unchecked bug builds report nothing; checked and unchecked outputs are identical for the correct
kernels). The 17 "FAIL" lines are the `agx-g13g --agx-strict` variants: G13 (M1) code checked by a simulator-only
option, which `agx_run_hw` does not have and a G14 GPU cannot run.

## 2. Cost

`b37_extra.py` (item 2): the suite's grid-copy kernel over 2^22 threads (256 per block), checked and unchecked, firmware
time from `agx_run_hw` (`hw_extra.json`, `hw_extra2.json`, 5 runs each, two batches):

| Build | Firmware time (ms) |
| --- | --- |
| unchecked | 0.284-0.295 |
| checked | 0.25-0.27 (2 runs), 0.445-0.465 (8 runs) |

**Median ratio 1.56 and 1.59**, close to the simulator's ~1.5x estimate. The two checked runs at ~0.26 ms (faster than
unchecked) are unexplained: battery-power clock states change between runs (`2026-10-16-battery-clock-states`), so
repeat on AC before quoting the fast mode. agx-bench's set was not timed (it is LLVM IR, not PTX, and needs its own
harness).

## 3. A second launch after a reported error does nothing: pass

Each bug kernel's checked build launched with the module's error record already claimed (`claimed = 1`, as after a
reported error), without zeroing it: off-by-one store, out-of-bounds atomic, threadgroup overflow, second block,
struct-pointer off-by-one. **On the GPU (and in agx_run) every output buffer kept its initial contents and the record
stayed claimed** (`hw_extra.json`): the kernels return at entry.
