# B31: cost of instructions issued with an empty execution mask (2026-10-20)

Blocker B31 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: masked-off ALU instructions cost about
as little as jumping over them, but masked-off memory instructions do not: a `device_load` + `wait` still costs about
a third of an active one, a masked `device_store` costs at least as much as an active one (and writes nothing), and a
masked `threadgroup_load` + `wait` about half.** So the backend may drop the jump over short ALU-only bodies, and should
keep `jmp_exec_none` over any body containing a load, store or wait.

`b31.py`: one SIMD group, a counted loop of 20,000 trips (`agx_loop` shape); each trip holds an `if` whose body is K
copies of one instruction class. Variants: `base` (no `if`), `empty` (condition never true, no jump), `skip` (Mesa's
`jmp_exec_none` over the body), `active` (all 32 lanes). Every program ran in `agx_run` first. Firmware time per
program = min over runs. 0 faults. In every `empty` and `skip` run, masked-off stores wrote nothing (0 / 32 words);
active ones wrote 32 / 32.

The GPU's clock state moves the base loop between 42 and 84 ns per trip between runs (simulator open problem S1), so
`rerun.jsonl` interleaves base / empty / skip / active in three rounds (min of 7 runs each). ns per instruction above
the base (K = 32; first pass in `results.jsonl` also has K = 8 and `simd_shuffle`):

| Class | empty (masked, no jump) | skip (jumped over) | active (32 lanes) |
| --- | --- | --- | --- |
| `iadd` | 1.7-3.9 | 1.6-2.4 | 3.9-5.4 |
| `fmadd32` | 1.2-2.5 | 1.7-3.8 | 2.6-5.8 |
| `device_load` + `wait 0` | **13.2-20.4** | 2.4-3.5 | 36.8-41.3 |
| `device_store` | **9.4-11.8** | 1.8-3.0 | 5.0-9.9 |
| `threadgroup_load` + `wait 0` | **13.4-16.3** | 1.7-2.1 | 22.9-28.5 |
| `simd_shuffle` (first pass) | 1.6 | 1.4 | 6.5 |

(The `skip` column includes the jump's own cost spread over K = 32.)

**For the cost model:** masked ALU instructions should cost about their issue slot, not their latency; masked memory
instructions keep a large fraction of their cost (the `wait` still waits, and a masked store is not free). The current
model's "full latency for everything" over-charges ALU bodies, which is what made dropping the jump look like a loss
(agx-bench 38,579 -> 40,221 cycles) for ALU-only bodies.
