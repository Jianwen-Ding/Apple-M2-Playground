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
* loads complete after the L1 latency (50 cycles, [load finding](../2026-10-10-agx-load-latency/README.md);
  `--load-latency` overrides) and `wait` drains a scoreboard slot;
* a taken backward jump costs 31 extra cycles, fit so an empty counted-loop trip costs the measured 35.3.

## Accuracy

| Dataset (stored hardware measurements) | Median abs. error | 90th pct | Max |
| --- | --- | --- | --- |
| 60 benchmark loops: latency (in-sample) | 1.9% | 5.1% | 5.2% |
| 60 benchmark loops: single-group issue (in-sample) | 2.5% | 5.8% | 10.1% |
| 60 benchmark loops: 4 groups per core (in-sample) | 4.0% | 11.8% | 47% (`.cache` forms) |
| register rotation, 32-bit, D = 4–16 | 3.5% | | 11.3% |
| **24 random kernels, 1 SIMD group (out of sample)** | **4.3%** | 14.5% | 14.8% |
| **24 random kernels, 4 SIMD groups per core (out of sample)** | **9.8%** | 18.3% | 24.0% |
| **held out: 24 new 24-instruction kernels, 1 group** | **4.6%** | 10.6% | 13.8% |
| **held out: same, 4 groups per core** | **9.8%** | 15.7% | 20.9% |
| **held out: 12 new 48-instruction kernels, 1 group** | **3.4%** | 7.0% | 8.1% |
| **held out: same, 4 groups per core** | **9.0%** | 13.9% | 18.0% |

**Measurement noise floor (4 groups per core).** Per-core span timings repeat to about ±6%: the same body
measured twice gave 49.7 / 46.8 (iadd chain) and 42.0 / 45.1 (fadd32 chain) cycles per trip, and the empty
loop 33.5–35.6 (35.3 with one group). Latency-bound chains at 4 groups per core came out 0.93–1.13 × their
single-group cost (`groups.json`), so ratios below 1 are noise, not speed-ups. The 4-group validation error is
therefore only modestly above what the measurement can resolve; single-group measurements repeat within ~1%.

Errors are prediction minus measurement relative to the measurement. The random kernels mix 52 of the
benchmarked forms with random register dependencies over r5–r12; they were not used for fitting, except
that the issue rule was chosen among three candidates by their score. The two held-out sets (new seeds 5000+
and 6000+, measured after every model choice was frozen) confirm the same accuracy:

| Issue-interval rule | random, 1 group | random, 4 groups/core | leader + k independent iadds |
| --- | --- | --- | --- |
| group-blocking (default) | 4.3% | 9.8% | 7.9% (max 42%) |
| shared complex pipe | 8.1% | 14.9% | 3.9% (max 14.5%) |
| per-unit family | 14.8% | 19.0% | 3.9% (max 14.5%) |

Residual analysis (24 random kernels, single group): the error correlates weakly with 16-bit writes
(+1.7 cycles each unexplained, r = 0.35), SIMD reductions (−2.5, r = −0.50) and transcendentals (−1.0, r = −0.24).
Targeted probes (`half.json`) rule out the obvious causes: mixed-width write-after-write costs ~0.87 per pair
in either direction, reading a fresh 16-bit result as 16 or 32 bits is an ordinary dependency, reductions
cost 23.8 cycles before an independent and 25.5 before a dependent successor (both as modelled), and a
separate 16-bit writeback time (17/22/26 cycles) leaves the random-kernel error unchanged. With 24 kernels
these correlations may be noise.

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
