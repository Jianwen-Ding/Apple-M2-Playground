# SIMD groups that exit early free their registers for the next workgroup, but not their group slots: occupancy is min(96 group slots / groups per workgroup, register cap for the live groups)

Status: confirmed on one device (M2 Max G14C), 2026-11-10, own probe kernel through agx_runtime (agx_run_hw
`--back-to-back 1000`, top clock). Nothing disassembled or decompiled.

## Test

`AGX-Performance-Simulator/scripts/probe_partial_wg.py`: N workgroups of 256 threads (8 SIMD groups). Lanes with
thread x >= 32 x ACTIVE jump to the end at once; the others run T trips of 8 dependent iadds. 108 register halves
(register cap 30 groups per core: 3 resident workgroups by the usual rule) or 32 halves (cap 96: 12 workgroups).

| N | regs | ACTIVE groups | T | hw us |
|---|---|---|---|---|
| 7168 | 108 | 1 | 50 / 200 / 800 | 39.0 / 141.9 / 553.8 |
| 7168 | 108 | 8 | 50 / 200 / 800 | 155.9 / 594.9 / 2341.9 |
| 7168 | 32 | 1 | 50 / 200 / 800 | 35.9 / 131.6 / 514.5 |
| 1140 | 108 | 1 | 50 / 800 | 9.4 / 106.0 |
| 1140 | 108 | 8 | 50 / 800 | 27.9 / 388.8 |

## Result

- With one working group per workgroup the 108-halves kernel runs ~3.5x faster than 3 resident workgroups would
  allow (a model with whole-workgroup register release: 1908 us at T = 800), and almost as fast as with 32 halves
  (12 resident workgroups by registers): the exited groups' registers are reused.
- But no more than ~12 workgroups run at once (96 group slots / 8 groups): the 32-halves kernel is no faster than
  its 12-workgroup register occupancy, and 108 halves reaches about the same. A workgroup keeps its 8 group slots
  until its last group ends; registers are held only by live groups (a new workgroup needs registers for all its
  groups at launch).
- llama.cpp's rope_neox (256-thread workgroups, only group 0 works when the head size is 64) behaves the same: 7168
  workgroups 33.4 us on hw; 3-resident waves predict 72.6, the rule above 33.5 (`rope-grid-sweep.txt`: hw per 3
  workgroups per core ~0.4 us).

## Implications

- Kernels whose workgroups end most of their groups early are not limited by the register allocation of those
  groups; a CUDA runtime's occupancy for them is the 96-slot (and 55-workgroup) limit.
- AGX Performance Simulator: `AGX_EARLY_EXIT` (default on) in `simulate_core_list` since 2026-11-10.
