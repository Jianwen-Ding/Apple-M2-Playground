# Transcendentals: which pairs mix freely depends on latency and a slow stage, not on a shared per-op cost

Status: one SIMD group: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM; 4 groups per core:
partly understood. Real cycles unless stated (1 reference unit = 1.049 cycles).

Found because the cost model's 4-group error correlated with `log2` (+0.46), `sin_pt_2` (+0.41) and
`convert` (+0.36) across 60 random kernels. The model charged each transcendental a fixed share of one
unit per core. Hardware does not.

## Throughput-bound pairs (8 independent chains, the two ops alternating)

| pair | 1 group: cycles / op | 4 groups/core: reference units per trip |
| --- | --- | --- |
| `log2`+`log2`, `floor`+`floor`, `log2`+`exp2` | 1.97–1.99 | 122 |
| `log2`+`rcp` | **1.97** (pure `rcp`: 2.94) | **122** (as pure `log2`) |
| `rcp`+`rcp` | 2.94 | 232 (4 chains instead of 8: 197) |
| `log2`+`floor` | **2.99** (worse than either alone) | 207, later 232 |
| `floor`+`rcp` | 2.91 | 194 |
| `rsqrt`+`log2` | 2.47 | 153 |
| `rsqrt`+`rcp` | 3.43 | 258 |

## Claims

1. **One SIMD group: a pipe with three rules** fits all nine pairs within 1.2%:
   * transcendentals issue at most one per **2 cycles** and occupy the group for 2 cycles (not their full issue
     interval: an `rcp` chain with 3 independent `iadd`s costs 72.6 units, chain-bound);
   * `rcp` and `rsqrt` also hold a **slow stage** for 3 and 4 cycles;
   * results are **written back in order, at least 2 cycles apart**. `floor` (latency 3) after `log2` (latency 5)
     waits for its writeback slot, so mixing latencies costs more than either op alone.
2. **4 groups per core: separate slow and fast units** with in-order writeback 1 cycle apart.
   `log2`+`rcp` costing the same as pure `log2` means `rcp` does not use the unit `log2` saturates.
   Unit costs come from the benchmark's 4-group rows (`rcp` 1.6, `rsqrt` 1.02, others 0.92 cycles), not from
   these probes; only the writeback gap was chosen on them (0 / 0.5 / 1.0 cycles). On the 14 probe cases the
   median error goes from ~17% to 7.3% (max 26%, `rsqrt`+`rcp`). Held-out random kernels at 4 groups:
   24 instructions 10.4% → 7.9%, 48 instructions 9.9% → 9.6%. A grid fit that used the probes for the unit
   costs (`sfu-coregrid.json`) needed `rsqrt` at 2.3 cycles and broke the `rsqrt` benchmark row (+126%).
3. **Not understood at 4 groups:** pure `rcp` costs 232 units with 8 chains but 197 with 4 (repeatable,
   `sfurepeat.json`); `rsqrt`+`rcp` costs 258 although `rsqrt` alone sustains ~1 per cycle per core. `log2`+`floor` measured 207 in one run and 232 twice later. The cost of mixing latencies
   across groups seems to depend on how the groups interleave.

## Effect on the cost model

Held-out random kernels, 1 group: unchanged (24 instructions 5.3% → 5.4%; 48 instructions 3.6% → 3.7%). The selection
set got worse (5.1% → 6.6%): the old 3-cycle group blocking for `rcp`, refuted by the probes, was offsetting part of
the model's general under-prediction on random code. A first version without any group blocking was worse on every
held-out set and was replaced.

## Reproducer and evidence

`python3 scripts/cost_probes.py sfupairs`; `results/2026-10-11-cost-model/sfupairs.json`, `sfumix.json`,
`sfuswitch.json`, `sfurepeat.json`, `sfu-coregrid.json`. Checked by `scripts/verify_cost_model.py`.

## Compiler implications

* Schedule transcendentals of equal latency next to each other: `log2`/`exp2`/`sin_pt_2`/`rcp` (5 cycles)
  interleave freely; putting `floor`/`rint`/`sin_pt_1` (3 cycles) between them costs up to 50% more.
* `rcp` is cheap when interleaved with `log2`/`exp2` and expensive back to back.
