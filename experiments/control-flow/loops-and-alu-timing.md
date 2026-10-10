# Counted loops, ALU latency/issue and core throughput: G14C B1 — 2026-10-10

Every run below went through the [direct DRM path](../baseline/direct-drm-compute.md)
(no Mesa/Vulkan). Every dispatch passed a whole-buffer oracle that proves the
exact trip count, and every loop was checked in an emulator before reaching the
GPU. `make verify-loops` checks all numbers here against
[retained evidence](../../results/2026-10-10-agx-loops/README.md).

## Loop encoding (works on hardware)

`scripts/agx_loop.py` builds a counted loop from Mesa's nested-loop pattern. The
control prefix leaves in-bounds lanes at r0l = 0 and out-of-bounds lanes at 1.

```
mov_imm r3, 0 ; mov_imm r4, K ; mov_imm r2, P (; r5..r7 = 0)
push_exec r0l, 1                ; if_fcmp r0l, eq, 0.0, 0.0, 1 — out-of-bounds lanes -> 2
top:
  <M chain steps, round-robin over 1/2/4 registers>
  iadd r3, 1, r3.sx
  while_icmp r0l, ult, r3, r4, 1 ; lanes with r3 >= K -> r0l = 1 (inactive)
  jmp_exec_any pc-<loop bytes>   ; loop while any lane is active
pop_exec r0l, 1                 ; finished lanes 1 -> 0, out-of-bounds 2 -> 1
```

* **The `push_exec` is essential.** Without it, finished lanes and out-of-bounds
  lanes both end at r0l = 1, and the post-loop store is lost.
* **Safety design.** The counter counts up and the loop continues only while
  `r3 < K`, so an inverted reading of the condition exits after one trip instead
  of hanging. The emulator runs applegpu's per-instruction `exec` semantics
  (branches resolved by the emulator) under a step limit. It catches a corrupted
  self-branch. The GPU runner refuses any loop whose emulated copy fails, or whose
  bytes differ from it anywhere except K's immediate.
* 567 loop submissions (559 retained + 8 regression; K from 1 to 100,000; 32 to 38,912 lanes) produced no
  timeout or fault. dmesg is unavailable (root needed); this rests on return codes
  and oracles.

## Results

### Lowest clock state (fresh process; K = 2000; M = 64 steps per iteration)

| | iadd (8 B) | fadd32 (4 B) |
| --- | --- | --- |
| Dependent chain | 4.475 ns/instr | 4.471 ns/instr |
| 2 independent chains | 2.258 ns (×1.98) | 2.253 ns (×1.98) |
| 4 independent chains | 2.263 ns (no gain) | 0.31 ns (*artefact, below*) |
| Empty loop (counter, `while_icmp`, taken `jmp_exec_any`) | 86.4 ns/iteration | |

**The 4-chain fadd32 figure is wrong as a throughput.** With M = 512 and K = 500,
4 chains cost exactly as much as 2 (634.6 µs each). With short bodies, part of the
per-iteration overhead overlaps with the chain work, so subtracting a constant
overhead is invalid. A 1-instruction body likewise disappears entirely: K =
1k→10k gives 85.6 ns/iteration versus 86.4 ns for the empty loop. Use bodies of
hundreds of instructions to measure instruction cost.

### Clock ladder and cycles

Long runs of the same kernel step through discrete levels, for example fadd32
dependent ×512: ~4.8 → 2.21 → 1.62 → 1.53 ms (plateau). The lowest/top ratio is
3.16, which matches 1398/444 MHz = 3.149. GET_PARAMS reports a 1,398 MHz maximum.
444 MHz as the lowest performance state is recalled from Asahi device trees, not
read here. Assuming the plateau is 1,398 MHz:

| per SIMD group, top state | iadd | fadd32 |
| --- | --- | --- |
| Dependent chain | 2.01 cycles | 2.01 cycles |
| ≥ 2 independent chains | 1.02 cycles | 1.01 cycles |
| Loop overhead | ~38 cycles / iteration | |

These ratios hold in every state, independent of the clock assumption:
dependent = 2 × independent, and independent = 1 instruction per issue slot.

### SIMD groups per core (fadd32, 2 chains, M = 512, K = 2000, top state)

| lanes | groups/core | time | single-group equivalents per core |
| --- | --- | --- | --- |
| 32 | 0.03 | 796.9 µs | 1 |
| 1,216 | 1 | 797.1 µs | 1 |
| 4,864 | 4 | 1,529 µs | 2.1 |
| 9,728 | 8 | 1,806 µs | 3.53 |
| 19,456 | 16 | 3,725 µs | 3.42 |
| 38,912 | 32 | 7,034 µs | 3.63 |

Cores run independently. A core saturates near 3.5–3.6 groups' worth of issue,
consistent with 4 schedulers × 32 lanes = 128 FP32 ALUs per core. At 32
groups/core the GPU sustained **5.67 × 10¹² fp32 adds/s, 83% of the non-FMA peak**
(38 × 128 × 1.398 GHz). Four groups per core gaining only ~2× is unexplained.
Uneven workgroup placement is one candidate.

## Compiler and runtime implications

* **Scheduling.** Dependent ALU ops cost 2 cycles; interleaving 2 independent
  chains reaches full issue rate. An AGX backend scheduler needs only distance-2
  separation between producer and consumer for these ops.
* **Branches are expensive (~38 cycles per taken loop iteration).** Unroll
  moderately: about 8–16 instructions per iteration amortizes the branch, while
  straight-line code costs ~1.8 ns/byte of fetch. Short bodies (≤ a few
  instructions) are hidden inside the branch cost entirely.
* **Occupancy.** At least 4 resident SIMD groups per core are needed to approach
  peak throughput (≥ 4,864 threads GPU-wide for ALU-bound kernels).
* **Benchmarking.** The clock ladder spans 3.15×. Warm up for tens of
  milliseconds and report the state (plateau) used.

## Not yet established

Latency of other classes (multiply, FMA, 16-bit, transcendental, memory loads),
`iadd`'s 64-bit forms, divergent loops (lanes with different K), and the
4-groups-per-core anomaly.

## Reproduce

```sh
make agx-loop-test   # emulator gate tests + 3 small hardware loops
make verify-loops    # offline: all numbers above
make agx-loops       # re-measure the matrix (~1 min of GPU time)
```
