# AGX cycle cost model (`agx_cost.py`), calibrated and validated on hardware

Status: tool + validation on one device (driver-reported M2 Max G14C B1). Predictions are in reference
units (dependent 8-byte iadd step = 2); real cycles = × 1.049 (see the instruction-bench correction).

## What it does

`python3 scripts/agx_cost.py code.bin [--groups G] [--annotate]` decodes an AGX binary with applegpu,
derives the dynamic path with applegpu's emulator (instructions it cannot execute are skipped; they do not
steer the counted loops and structured control flow used by Mesa), and simulates one core running G SIMD
groups cycle by cycle. `--annotate` prints per instruction the execution count, stall cycles and unit class;
taken-branch cost is attributed to the jump. `scripts/agx_capture.py` uses it to annotate shaders captured
from Mesa (see `docs/shader-capture.md`).

Model (every parameter measured on this GPU):

* per class latency, per-group issue interval and per-core throughput from the 60-form instruction bench,
  choosing the operand variant (immediate / `.cache` / register) that matches the instruction;
* per core: ≤ 4 issues per cycle, ≤ 4 32-bit register-operand reads per cycle (16-bit reads free), and per
  execution unit at most the best rate any of its operand variants reached;
* an issue interval blocks the whole SIMD group (the "group" rule; see accuracy below for alternatives);
* the 8-entry per-group result cache with ~17-cycle register-file writeback
  ([finding](../2026-10-11-result-cache/README.md)) and a 1-cycle 32-after-16-bit partial write hazard;
* device loads complete after the measured fast or slow load-to-use time (47 / 65 real cycles), deferred by
  ALU work issued while they are pending (see Memory below;
  `--load-latency` overrides) and `wait` drains a scoreboard slot;
* an idle `wait` costs 4.9 units inside a loop of <= 512 bytes and 10.9 otherwise
  ([wait finding](../2026-10-11-wait-cost/README.md));
* a taken backward jump costs about 33 extra real cycles, fit so an empty counted-loop trip costs the measured 35.25 units.

## Accuracy

Revised after an independent review (decode, units, method; see "Revision" below). Errors are |prediction −
measurement| / measurement, medians unless stated, from `make verify-cost-model`. "Body only" removes the
fitted empty-loop cost (35.25 units, predicted 35.27) from both sides, which is the fairer figure.

| Dataset | Role | 1 group: whole trip | 1 group: body | 4 groups/core: whole trip | 4 groups/core: body |
| --- | --- | --- | --- | --- | --- |
| 24 random 24-instr kernels | selection (issue rule chosen here) | 5.1% (max 15%) | 7.1% (max 23%) | 11.4% | 15.4% |
| **24 new 24-instr kernels** | **held out** | **5.3%** (max 12%) | **7.8%** (max 20%) | **10.4%** | **13.6%** |
| **12 new 48-instr kernels** | **held out** | **3.6%** (max 8.4%) | **4.3%** (max 11%) | **9.2%** | **10.8%** |

Fitting sets (not evidence of accuracy): the 60 benchmark loops reproduce to 0.4% latency / 0.4% issue /
1.9% per-core throughput; the register rotation used to fit the result cache to 1.7% (32-bit); the memory
probes to 1.5%. The model under-predicts kernels systematically (bias −2% to −5% with one group, −9% to −11%
with four), and the 4-group figures sit near the ±6% repeatability of the 4-group measurement itself.

Issue-rule choice (made on the selection set, before the revision; whole-trip medians):

| Issue-interval rule | random, 1 group | random, 4 groups/core | leader + k independent iadds |
| --- | --- | --- | --- |
| group-blocking (default) | 4.3% | 9.8% | 7.9% (max 42%) |
| shared complex pipe | 8.1% | 14.9% | 3.9% (max 14.5%) |
| per-unit family | 14.8% | 19.0% | 3.9% (max 14.5%) |

**Revision (after review).** Registers now come from applegpu's operand objects (vector loads/stores and
16-bit pairs were previously dropped); atomics are decoded from their fields; every descriptor has an explicit
class (texture, iterator, async, stack, tile, barrier, `stack_adjust`), unknown ones raise; stores hold a
scoreboard slot; parameters are in real cycles and stay fractional (0.1-cycle simulation ticks, because 8-byte
chains really take 2.1 cycles per step); each instruction's issue interval is charged to itself and waits
to the waiting instruction; the immediate-operand variant is used only with at most one register source;
the partial-write rule applies only between 16- and 32-bit writes; the trace flags loops whose condition
depends on uniforms or on instructions the emulator cannot run (their trip count is then unknown).
Classes without hardware data (texture, iterator, threadgroup and stack memory, tile, barriers,
threadgroup atomics) reuse device-memory or 1-cycle costs and are reported as `unmeasured`.

Memory parameters: device loads follow the [load-after-ALU finding](../2026-10-11-load-after-alu/README.md)
(fast 44.8 units with no ALU work since the last wait, ~63 after ALU work, completion deferred by ALU work in
flight; fit on the 30-point `load-alu-grid.json`). That also resolves the earlier gap to the 2026-10-10 chase
(~50 cycles): the chase measured the fast case. A second independent load costs +2.6, stores to one address
35 units each (+4.7 with a wait; only the repeated-address case was measured).

Residual analysis (24 random kernels, single group): the error correlates weakly with 16-bit writes
(+1.7 cycles each unexplained, r = 0.35), SIMD reductions (−2.5, r = −0.50) and transcendentals (−1.0, r = −0.24).
Targeted probes (`half.json`) rule out the obvious causes: mixed-width write-after-write costs ~0.87 per pair
in either direction, reading a fresh 16-bit result as 16 or 32 bits is an ordinary dependency, reductions
cost 23.8 cycles before an independent and 25.5 before a dependent successor (both as modelled), and a
separate 16-bit writeback time (17/22/26 cycles) leaves the random-kernel error unchanged. With 24 kernels
these correlations may be noise.

**Shared transcendental unit (sfumix.json, sfuswitch.json).** At 4 groups per core, independent `log2`,
`floor`, `rcp` contend like four `rcp`s do (148 vs 95 units per trip with one group), so the transcendental
classes share one unit per core. The model draws them from one shared bucket (each instruction costing
1 / its measured rate), and likewise imad/bitfield/convert. This moves that case from 89 to 110 predicted,
but hardware is at 148; `rcp`+`fadd32`+`imadd` (109 measured vs 84–87 predicted) is also unexplained. With
one group there is no function-switch cost (`log2`/`exp2` alternating = 4 × `log2`).

Known gaps: all rules under-predict random kernels (bias −4% with 1 group, −9% with 4), so some
contention is missing; a multi-cycle instruction followed by independent simple ALU instructions overlaps
on hardware more than the default rule allows; bfi/imadd followed by 4–8 iadds costs ~1–2 cycles more than
any rule predicts; 16-bit writeback beyond 9 registers, memory beyond L1, divergence, and more than
4 groups per core are not modelled. Clock changes are not modelled: predictions are cycles, not time.

## Reproducer and evidence

* `make verify-cost-model` (offline, re-scores every stored measurement).
* `make cost-calibrate`, `make cost-validate` (hardware) and `scripts/cost_probes.py lead|rotation|pairs|half|values`.
* Evidence: `results/2026-10-11-cost-model/` (`calibration.json`, `random-kernels.json`, `lead-plus-k.json`,
  `rotation.json`, `pairs.json`, `fetch-body-size.json`, `values.json`).
