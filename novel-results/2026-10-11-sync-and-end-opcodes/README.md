# 0x78 is a (4-SIMD-group) barrier; 0x18 is a fixed-cost op of unknown target; the ending opcodes are indistinguishable

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Builds on the [opcode descriptions](../2026-10-11-opcode-descriptions/README.md). Faulting
opcodes were not run (the probe refuses them), and no run faulted.

## Claim and scope

### 0x78: a threadgroup execution barrier

In one workgroup of 2 or 4 SIMD groups, group g delays for 1 + g·20,000 loop trips, stores a
flag, executes the candidate once, and then reads the slowest group's flag. Every group
executes the candidate exactly once, so a barrier cannot deadlock.

| Candidate | Flag in device memory | Flag in threadgroup memory |
| --- | --- | --- |
| `wait 0` | not seen (sentinel) | not seen |
| `memory_barrier` (Mesa `f596`) | not seen | — |
| `threadgroup_barrier` (`6800`) | **seen** | **seen** |
| **0x78** (`7809` and `7800`) | **seen** | **seen** |
| 0x18 (`1809`, `1800`, and after `memory_barrier`) | not seen | not seen |

**Correction (stress test):** 0x78 synchronizes only aligned blocks of 4 SIMD groups (128 lanes),
while 0x68 synchronizes the whole workgroup. See [0x68 vs 0x78](../2026-10-11-barrier-0x68-vs-0x78/README.md).
Within up to 4 groups, 0x78 makes every group wait, as 0x68 does, and earlier device-
and threadgroup-memory writes are visible after it. It is cheaper: 2.9 ns per execution
for a lone SIMD group, against 9.3 ns for 0x68, in the same state. It completes the
`xxxx1000` control family next to `threadgroup_barrier` 0x68.

### 0x18: fixed cost, waits for nothing tested

Counted loops of 50,000 trips, extra time per use (fast clock state):

| After… | `wait 0` | **0x18** | 0x78 | 0x68 | Mesa memory/device barriers |
| --- | --- | --- | --- | --- | --- |
| nothing | 1.4 ns | **4.3** | 2.9 | 9.3 | 68.7 / 71.9 / 80.1 |
| own device load | **22.8** (waits) | **4.3** | 2.9 | 9.4 | same |
| own device store | 1.5 | **4.3** | 2.9 | 9.4 | same |
| own threadgroup load / store | 0.0 / 0.0 | **4.3 / 4.3** | 2.9 / 2.9 | 9.4 / 9.3 | 68.7 |

0x18 does not wait for this SIMD group's device loads, device stores, threadgroup-memory
loads or stores, or atomics (within noise). It does not synchronize SIMD groups. It costs
4.3 ns in every case (6 cycles if the clock is at the 1,398 MHz GET_PARAMS maximum), on 1 core or spread over 8. With 8 SIMD groups contending for
one core its cost rises (to 17.9 ns), but so does `wait`'s in some runs, so that number is not
evidence of a shared unit. **What 0x18 synchronizes is still unknown.** The remaining
candidates need paths this harness does not have: textures/samplers, stack (spill)
memory, uniform stores, or fragment-stage resources.

### The 18 ending opcodes cannot be told apart

The 16 "ends" opcodes plus 0x98 and 0xf8 behaved identically in every test so far:

* 8 operand encodings and 6 exec-mask/group variants: they end the whole SIMD group whatever
  the mask, and nothing else ([earlier finding](../2026-10-11-opcode-descriptions/README.md)).
* **Pending stores:** all 16 stores issued just before them, with no `wait`, reach memory
  (the same as `stop`).
* **They end by themselves:** followed by 16 `stop`s, with lanes 0–15 active, they end all 32
  lanes. A forward skip onto `stop` would end only lanes 0–15.
* **Cost:** ending 2,048 one-group workgroups takes 6.7–7.0 µs (minimum) with each of them
  and with `stop`. There is no slow exception path.

Their only difference from `stop` remains mask independence. Not tested, on purpose: a
SIMD group ending while another waits at a threadgroup barrier (possible deadlock, i.e. a
GPU fault), ending inside the preshader, and fragment shaders.

### Method findings

* **Threadgroup memory works on direct DRM** with USC Shared word
  `0x4d | 1<<8 | 0x24<<10 | (bytes/256)<<24` (4 KiB = `0x1000914d`). Loads and stores are
  packed as in Mesa `agx_pack.c:769-792` (`0x29` store / `0x69` load, 8 bytes). A
  1/2/4-group exchange through `threadgroup_barrier` was exact.
* **Timing:** short dispatches (< 1 ms) flip between two GPU states (2.2×) during a session,
  with the same core (SR20) every time. 50,000-trip dispatches (6.5 ms) settle at a hard floor
  that varied < 1.5% over 50 processes; interference only adds time. **Use the minimum of
  long dispatches.**

## Reproducer and evidence

`make sync-probe` (hardware, `CONFIRM_GPU_FAULTS=1`), `make test-sync-and-end` (hardware
subset; [test](../../tests/test_sync_and_end.py)), `make verify-sync-and-end` (34 offline
checks). [Evidence](../../results/2026-10-11-sync-and-end-opcodes/README.md).

## Relationship to existing knowledge

Mesa names `threadgroup_barrier` 0x68 and never emits a SIMD-group barrier (Copilot's
source analysis: `agx_compile.c:1509-1549`). It has no name for 0x18 or 0x78, and neither
does applegpu. OpenCode's literature search found no public description of either, and none
of what `threadgroup_barrier` does after a group has exited. The Asahi kernel exposes only
MMU, timeout and channel faults (`drivers/gpu/drm/asahi/gpu.rs`, `regs.rs`), which fits
ending opcodes that complete normally.

## Compiler implications and limitations

* A PTX `bar.sync` must use 0x68: 0x78 covers only 4 SIMD groups (see the stress test).
* The PTX `exit` in divergent code: `stop` ends only active lanes, while the 18 ending
  opcodes end the whole SIMD group. Keep `stop`.
* Only one device was tested; G13/G14D may differ.

## Update 2026-10-16: 0x18 after an atomic with return and after the invalidating barriers

**Test:** simulator task safe-08 step 3, `run_drm_sync_probe.py --suite wait18`.
- Every job first ran to completion in the simulator's `agx_run`.
- The GPU clock was held at its top state by a background stream of 64-lane delay commands (the "clock keeper",
  `results/2026-10-16-fixed18-waits/keeper.sh.snapshot`). Each reference then stayed within 1 ns per trip across
  its six placements. Without the keeper the reference minimum jumped between clock states by > 30 ns per trip.

| After… | `wait 0` | **0x18** |
| --- | --- | --- |
| device atomic add **with return** | **67 ns** (waits for the returned value) | **4.4 ns** |
| `unknown_barrier_1` (f533, the cross-core release) | 1.5 ns | **4.3-4.5 ns** |
| `device_barrier_1` (f59d, the acquire / invalidate) | 1.4 ns | **4.3-4.4 ns** |
| device store, then f533 | 3.5 ns | **5.0-5.1 ns** |

0x18 still costs a fixed ~4.4 ns (≈ 6 cycles at 1,398 MHz), whatever precedes it. It does not wait for returned
atomics or for either invalidating barrier. What it synchronizes remains unknown. The remaining candidates need
texture / sampler, stack, uniform-store or fragment-stage paths.

The 403 undecoded-opcode cases (all eight operand encodings, plus the ends opcodes inside a branch) are now part of
the simulator's coverage suite (`coverage/expected/undecoded`). All are deterministic and match the simulator
exactly.

Reproduce: `make fixed18-waits` (GPU, with the keeper) and `make verify-fixed18-waits` (offline, 12 checks).

**Ending opcodes at scale (2026-10-16, safe-08 step 4).** With the clock keeper running, 2^20 lanes (32,768
one-SIMD-group workgroups) whose body is only the ending instruction:
- `stop`: 84.4-86.7 µs;
- each of the 16 ends opcodes, 0x98 and 0xf8: 85.7-87.0 µs (fastest of 16 repeats, two trials).
They are still indistinguishable: there is no slow exit path, and SIMD-group slots are freed equally fast.
