# Instruction benchmark suite: latency, issue rate and per-core throughput for 60 instruction forms

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
309 dispatches, no fault or timeout. Only instruction forms that already ran on hardware were used.

## Method

`scripts/run_bench.py` times every instruction inside one dispatch, so GPU clock changes cancel:

* Each SIMD group reads the CPU-written 24 MHz timer ([in-shader clock](../2026-10-11-in-shader-clock/README.md))
  around five counted-loop phases: REF(16), REF(64), OP(16), OP(64), REF(16), after a 2–6 ms warm-up.
* REF is the dependent `iadd x, x, 1` chain, 2 cycles per step ([loop finding](../2026-10-10-agx-loop-alu-timing/README.md)).
  The 64-minus-16 slope removes loop and timer overhead; REF's slope is ns per cycle at that moment.
* **Latency:** one SIMD group, one dependent chain. **Issue interval:** one SIMD group, 8 independent
  chains (cycles per instruction). **Per-core throughput:** 152 SIMD groups (usually 4 per core),
  8 chains each, analysed **per core** (SR20). Each phase is timed from the first of the core's groups
  entering to the last leaving, because groups sharing a busy unit are not scheduled fairly.
* Acceptance gates: single-group runs need the opening and closing REF within 2%; GPU runs need two
  independent dispatches to agree within 5% (worst case 2.7%). All 60 × 3 measurements passed.
* Every accepted run ran at 1,277–1,341 MHz (median about 1,333). Cycle figures rest on the
  2-cycle iadd reference; the 0.95-cycle issue of `fadd32 x, x, 0.125` suggests about ±5% absolute scale.

## Claim and scope

**Core issue and lanes.** A core completes up to **about 4 SIMD-group instructions per cycle
(128 lanes)**. This is reached by forms with at most one 32-bit register source: `mov_imm`,
`iadd x, x, 1`, `fadd32 x, x, 0.125` (133 lanes), `fmadd32 x, x, 0.5, 0.125` (123), fp16 add/mul (123)
and `quad_shuffle` (121). This matches Apple's 128 FP32 lanes per core.

**Register operands limit throughput.** The same operations with 32-bit register sources fall to
about **2 instructions per cycle per core with two register sources** (`iadd`, `and`, `xor`, `fadd32`,
`fmul32`: 63–65 lanes) and **1.4 with three** (`fmadd32`: 44 lanes). This is consistent with about four
32-bit register-operand reads per core per cycle. The `.cache` hint on a constant operand did not help
here, and it halved single-SIMD issue (2.03 instead of 1.04 cycles).

**Execution classes (latency / issue interval per SIMD group / core throughput):**

| Class | Latency | Issue interval | Lanes / cycle / core |
| --- | --- | --- | --- |
| int add/sub/logic, fp32/fp16 add/mul/fma, compare-select | 2 | 1 (fma32, select: 2) | 64 (register) to 128 (immediate) |
| integer multiply-add, bitfield/shift, popcount/bitrev/ffs, convert, floor/rint | 3 | 2 | 30–36 (one 32-lane unit) |
| 64-bit add, 32×32→64 multiply-add | 3.9–4.8 | 3.9 | 15–17 |
| rcp | 4.8 | 2.9 | 21 |
| log2, exp2, sin_pt_2 | 4.8 | 1.9 | 36–37 |
| rsqrt | 5.7 | 3.8 | 33 |
| simd_shuffle (any form), ballots | 4.8 | 2 | 46–72 |
| quad_shuffle | 3.9 | 1 | 121 |
| quad reduction (`quad_iadd`) | 11.5 | 8.7 | 15 |
| SIMD reductions (`simd_iadd/fadd/min`) / prefix scan | 22–23 / 17 | = latency (no overlap) | 5.6–7.4 |

Full per-instruction table: [table.md](../../results/2026-10-11-instruction-bench/table.md).

Not established: throughput beyond 4 SIMD groups per core. Two attempts failed (see failed
approaches), so the reduction and transcendental figures may rise with more groups. Also not
covered: value-dependent timing (chains used benign values), memory instructions (see the
load-latency finding), and fp16 forms with register-pressure effects.

## Reproducer and evidence

`make bench` (hardware, about 30 min), `make verify-bench` (offline, 0 failures).
`scripts/bench_report.py` regenerates the table. [Evidence](../../results/2026-10-11-instruction-bench/README.md).

## Compiler implications

* Fold constants into immediates wherever the encoding allows. A register constant halves FP32
  and integer throughput, and FMA with register operands runs at about a third of peak.
* FP16 arithmetic reaches full rate with register operands, so prefer it where precision allows.
* Schedule dependent ALU instructions at least 2 apart (3 for imad, bitfield, convert; 5–6 for
  transcendentals and shuffles).
* SIMD reductions cost about 23 cycles and serialize per SIMD group. Implement `__reduce_*_sync`
  and warp scans so that independent reductions come from different SIMD groups, or use
  shuffle trees (4.8-cycle latency, 2-cycle issue) when several values are reduced at once.
* 64-bit adds cost about 4× a 32-bit add; keep address arithmetic 32-bit where possible.
