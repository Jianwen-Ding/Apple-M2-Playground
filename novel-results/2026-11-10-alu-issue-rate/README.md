# With 8+ SIMD groups a core issues ~2 ALU instructions per cycle and reads ~2.4-3 registers per cycle

Status: confirmed on one device (M2 Max G14C), 2026-11-10, own probe kernels (AGX-Performance-Simulator
`scripts/probe_tg_alu.py`, `scripts/probe_sustained.py`) through agx_run_hw back to back (warm-up run first).
One workgroup of NG SIMD groups per core on 32 cores; times are the slope between 1000 and 3000 loop trips, in
cycles of 1398 MHz per trip on the core. Each trip: 8 (or 4) ALU instructions on 8 independent accumulators
r21..r28 + 3 loop instructions (iadd, while_icmp, jmp_exec_any). Nothing disassembled.

## Result

| pattern (per trip) | registers read | 4 groups | 8 | 16 | 32 |
|---|---|---|---|---|---|
| 8 x `iadd rT, rT, 1` | 1 | 46.0 | 45.9 | 87.5 | 171.1 |
| 4 x `iadd rT, rT, 1` | 1 | 42.1 | | 53.3 | |
| 8 x `fmadd32 rT, rT, rT, rT` | 1 | 46.0 | | 87.6 | 171.3 |
| 8 x `fmadd32 rT, rT, r29, r29` | 2 | 61.0 | | 113.8 | 220.8 |
| 8 x `fadd32 rT, rT, r30` | 2 | 59.2 | | 115.1 | 228.5 |
| 8 x `iadd rT, rT, r30` | 2 | 49.1 | | 127.1 | |
| 8 x `fmadd32 rT, rT, r29, r30` | 3 | 73.3 | 80.0 | 145.0 | 314.3 |
| 4 x `fmadd32 rT, rT, r29, r30` | 3 | 54.0 | 53.4 | 81.8 | 170.6 |

- 1-2 groups per core run at the single group's latency-bound rate (~5 cycles per instruction), as modelled.
- From 8 groups up the core is throughput bound: 16 groups x 11 instructions in 87.5 cycles = **2.0 instructions per
  cycle per core** with one register operand, whatever the unit (integer add or fp32 FMA).
- Each extra distinct register operand costs: 2-register forms 114-127, 3-register 145 cycles at 16 groups:
  **~2.4-3.0 32-bit register reads per cycle per core** (counting every distinct source register once).
- No all-core slowdown: the same loop (8 fmadd32, 8 groups) takes the same time with 1, 8 or 32 workgroups (one per
  core) and stays linear in the trip count up to 6.9 ms per command (`probe_sustained.py`): no clock drop under
  all-core load at these lengths.

## Implications

- ALU-bound code with many resident groups saturates at ~2 issues and ~2.5-3 register reads per cycle per core, half
  of what the four 1-per-cycle schedulers suggest. Kernels with heavy register-operand traffic (3-source FMAs on
  distinct registers) get ~1 FMA per cycle per core.
- AGX Performance Simulator (4 issues per core, 2 reads per cycle per half) is 30-45% fast for these probes at 16-32
  groups. AGX_ISSUE_PER_CORE=2 AGX_HALF_READ_PORTS=1.3 fits them (within 6%, the 2-register iadd -18%), but on real
  kernels the issue cap overshoots many Halide stencils (held-out median 5.5 -> 7%); the read limit alone
  (AGX_HALF_READ_PORTS=1.3) is neutral overall (cfd compute_flux -29 -> -10%, srad -20 -> -5%, but h_conv / h_compositing
  +20-30%). Real code must hit a cache or bypass that the probes do not; not adopted.

## Reproducer and evidence

`NG="1 2 4 8 16 32" T1=1000 T2=3000 python3 scripts/probe_tg_alu.py both ffffffff iiiiiiii ffff` and
`... aaaaaaaa jjjjjjjj gggggggg kkkkkkkk iiii` (letters in the script's docstring); `B2B=100 T="2000 20000 120000"
N="1 8 32 38" python3 scripts/probe_sustained.py both`. [Evidence](../../results/2026-11-10-alu-issue-rate/).
