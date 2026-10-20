# B34: stack load / store cost and the scoreboard wait groups (2026-10-20)

Blocker B34 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`, now runnable because direct-DRM scratch works
(B1). **Results: a stack load costs the same as an L1-hit device load when waited on (~33 ns), but independent stack
loads pipeline at ~3 ns each behind one wait; there are two scoreboard groups and `wait N` covers only group N; a
register read before its group's `wait` returns the old value (no interlock).** 0 faults.

## Wait groups (`waitgroups.py`, 2 runs per case on the GPU)

r20 = sentinel; a cold device load (a lane-distinct word 4 MiB+ into the table, never touched) into r20 in group S; a
warm load in the other group F; `wait F`; copy r20 out; `wait S`; store r20.

| Slow load group S / waited group F | r20 right after `wait F` | r20 after `wait S` |
| --- | --- | --- |
| 0 / 1 | sentinel in 32/32 lanes (both runs) | loaded value, 32/32 |
| 1 / 0 | sentinel in 32/32 lanes (both runs) | loaded value, 32/32 |

- The encodings carry a single scoreboard bit: `device_load 2..7` / `stack_load ..., 2` / `wait 2..7` assemble to
  slot 0 or 1 (`agx_asm` round trip), so there are **two groups**.
- **`wait N` waits for group N only**, in both directions; nothing stalls a read of a pending destination.
- **Simulator fix:** `agx_run` completed slot-0 loads immediately (so `wait 1` appeared to cover slot 0). It now
  defers every load to the `wait` on its slot (`rust/src/func.rs`) and reproduces both rows. `make test`,
  `verify-cost-model` (identical), `coverage-check`, `spirv-sim` and `verify-traces` give exactly the same results as
  before the change (the latter three have the same pre-existing failures with and without it: spirv-sim 5 workloads,
  verify-traces 652 / 721, coverage-check 2,654 / 2,681).

## Cost (`stackcost.py`; one SIMD group, Mesa's `stack_adjust #80` with `AGX_SCRATCH_DWORDS=80` and Mesa's helper;
20,000 trips x 16 instructions, min of 7 runs, 3 interleaved rounds; `cost.jsonl`)

| Body (x16 per trip) | ns per instruction above the empty loop (3 rounds) |
| --- | --- |
| dependent `stack_load` + `wait 0` | 32.9, 33.6, 32.9 |
| dependent L1-hit `device_load` + `wait 0` | 32.9, 33.6, 32.9 |
| 16 independent `stack_load`, one `wait 0` | 2.6, 3.3, 2.6 |
| 16 independent `device_load` (L1 hit), one `wait 0` | 24.3, 25.0, 24.3 |
| 16 `stack_store`, one `wait 0` | 1.6, 2.3, 1.6 |

**For the backend:** put spill reloads in their own group and issue them together before a single wait (16 reloads
cost about one load latency plus ~3 ns each); never read a reloaded register before its group's wait. **For the cost
model:** `stack_load` latency is about that of an L1 hit (~33 ns, ~46 cycles at 1,398 MHz), issue ~3 ns; `stack_store`
~2 ns; the earlier ~2,000-cycle stall guess for spill reloads is far too high.
