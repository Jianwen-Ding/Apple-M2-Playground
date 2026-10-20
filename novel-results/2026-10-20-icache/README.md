# Instruction cache: 12 KiB per core, 64-byte lines, ~19% capacity lost for instructions that cross 8-byte boundaries; a 32-entry per-core taken-jump structure

Status: one device (driver-reported M2 Max G14C B1), direct DRM. Straight-line `iadd` / `and` / `mov_imm` bodies in Mesa's
counted-loop shape, gated in the applegpu emulator and the Rust simulator, with every hardware output oracle-checked.
SR20 (cluster/core) is recorded per group. 0 faults, hang budget unused. This is the first direct measurement of AGX
instruction-cache structure in this project; an earlier note only said that unrolled code is fetch-bound.

Method: one SIMD group (or a chosen few) runs a counted loop whose body is B bytes of independent instructions over 4
registers (fewer than the 9 destinations that trigger the result-cache slowdown). Each run executes about 3M body
instructions and is timed with firmware timestamps. **No clock keeper** (see
[failed approaches](../../notes/failed-approaches.md)): its kernel can share the probe's core. Each size runs 8-16
back-to-back dispatches, and the minimum or the median of the settled repeats is used.

## Results

| Question | Result |
|---|---|
| In-cache rate | 0.745 ns per independent `iadd` per group, about 1 per cycle at 1,398 MHz |
| **Capacity** | **12 KiB**: a 12,284-byte loop starting on a 64-byte boundary (192 lines) runs in cache; 12,292 bytes (193 lines) misses. Dense 8-byte scan, 353 sizes |
| **Line size** | **64 bytes**: shifting the loop start changes the outcome exactly at 64-byte line counts (130-run start-offset sweep, model 0 mismatches) |
| **Instruction alignment** | lines whose instructions cross 8-byte boundaries cost about 192/161 = **1.19×**: 8-byte or 4-byte instructions all shifted by 2 or 4 bytes fit only **161** lines; 4-byte instructions at 0 mod 4 (no crossing) fit 192; 6-byte streams 168-169 |
| Mixed alignment | proportional: aligned fraction f fits floor(192 / (f + 1.19 (1 - f))) lines: 167 / 175 / 183 for f = 0.25 / 0.5 / 0.75 (measured exactly) |
| Beyond capacity | gradual: rises to the streaming cost by ~20 KB, which suggests replacement other than strict LRU |
| Streaming cost | 3.1 ns per 8-byte instruction (0.39 ns/byte); 0.48 ns/byte for 6-byte and 0.53 for 4-byte instructions, so neither bytes nor instructions alone set it. Flat from 1 to 152 groups GPU-wide: no global fetch bottleneck at this scale |
| **Sharing** | **per core**: two SIMD groups on one core running different loops (one aligned, one misaligned) both fit through 5,376 B each and miss from 5,632 B, matching 85 + 85×1.19 ≤ 192 < 89 + 89×1.19. Different code on different cores (SR20 0x30 / 0x31) does not interact |

### Anomaly: two groups, same loop

Two SIMD groups of one workgroup running the *same* in-cache loop sometimes fall into a state 2-3.5× slower: 63 of 257
sizes between 4 and 12 KB. The state depends on loop length and changes between repeats; at 10,240 bytes, repeats
alternated between 0.75 and 2.85 ns. A single group never shows it. With 4 or more groups per core it disappears, and the
core's issue limit takes over (4.6-5.4 instructions/ns per core, 3.3-3.8 per cycle). One possible explanation, not
established, is a phase-dependent conflict in fetch arbitration.

### Taken-jump target structure: 32 entries per core

A loop of n blocks joined by taken `jmp_exec_any` (`scripts/probe_icache_assoc.py`):

| Question | Result |
|---|---|
| Cost of a taken jump within capacity | ~33 ns per 1-line block of 7 `iadd`s, about **39 cycles** per jump for a lone group (matching the loop-trip cost), at every block stride from 64 B to 16 KB |
| **Capacity** | **32 taken jumps per loop iteration**: 33+ cost more per jump, gradually (34: 50 ns, 48: 96 ns, 96: 124 ns per block, about +127 cycles). With 2-line blocks the limit is the same 32 jumps although only 64 lines are in use, so it counts jumps, not lines |
| **Sharing** | **per core**: two SIMD groups running different jump chains slow from 17 jumps each (16 + 16 = 32 fit); a shared chain still fits 32 |
| Cache associativity | no set aliasing: 4-line blocks at strides of 256 B, 4, 8 and 16 KB behave identically (32 blocks fit, 48 blocks = 192 lines miss). A plainly indexed cache would put 32 blocks into the same few sets, so the cache is highly associative or uses a hashed index |

**The capacity depends on jump spacing.** Loops of n blocks of L contiguous lines (each block ends in a taken jump to the
next): with L = 3-6 (jumps ≤ 384 B apart) 32 jumps fit and the 33rd costs more; with **L = 7-10 (448-640 B apart) only 16
fit** (17 is the first slow count at L = 7, 8, 9 and 10, whatever the total line count). For longer blocks the line
capacity limits first, at about 170-180 lines once jumps are involved. The mechanism (an address-indexed structure, or
entries that cover a window of lines after each target) is not established.

**What the structure counts, and what any jump costs.** Exact 64-byte blocks of 8 ALU instructions plus a 6-byte slot:

| Slot | ns per block (1 group) | 32-jump limit |
|---|---|---|
| a 6-byte ALU op (no jump) | 8.3 | — |
| `jmp_exec_none pc+6`, never taken | **34.1** (flat to 128 blocks) | no |
| `jmp_exec_any pc+6`, taken to the next instruction | 33.6, rising beyond 32 | **yes** |

So **every `jmp_exec_*` costs about 35 cycles of latency per SIMD group, taken or not**: fetch appears to stall until the
jump resolves, with no prediction or fetch-ahead past it. This is the ~38-cycle loop-trip cost of the
[loop finding](../2026-10-10-agx-loop-alu-timing/README.md). At full occupancy other groups hide the untaken case (the
[fp32-ieee layout probes](../2026-10-20-fp32-ieee/README.md) measured about 1 instruction of throughput). A **taken** jump
also occupies the 32-entry structure, whatever its distance, and costs throughput.

Compiler implication: keep the taken branches of a hot loop, across all code resident on a core, at **≤ 32**,
and **≤ 16** when they are more than ~6 lines (384 B) apart.
At low occupancy every `jmp_exec_*`, taken or not, is a ~35-cycle bubble, so merge guards and prefer predication
(`icmpsel` / `fcmpsel`) over short structured ifs. Fully unrolled
branchy code (unrolled `switch` dispatch, many guards) pays up to about 166 cycles per taken jump beyond that.

## Compiler implications

- Keep hot loops under about **10 KB** (161 lines × 64 B: the worst-case alignment); 12 KiB is the best case.
  All SIMD groups resident on a core share this budget when they run different code.
- AGX instructions are 2-12 bytes long, so 8-byte-boundary crossings are common. Aligning loop starts to 64 bytes only
  removes the extra partial line; it does not remove the crossing cost.
- Code beyond the cache streams at about 0.4-0.5 ns per byte per group. Large unrolled bodies are fetch-bound, so
  prefer loops for long straight-line code at low occupancy.

## Not established

Miss latency (jump-target lines streamed at about 33 ns per line, but partial retention spoils a clean fit), the
mechanism behind the 1.19× crossing cost (perhaps per-chunk pre-decode storage), the replacement policies,
the jump structure's exact role (target buffer or fetch redirect),  miss latency, whether prefetch is sequential, and the cause of the two-group anomaly.

## Reproduce

`python3 -B scripts/probe_icache.py [--sizes ...] [--pad P] [--kind iadd8|and6|mov4] [--shift-at F] [--groups G --local L] [--dual]`
(do not run `clock_keeper.py` at the same time). Offline: `make verify-icache` (19 checks against
[results/2026-10-20-icache](../../results/2026-10-20-icache)).
