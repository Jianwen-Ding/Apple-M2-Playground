# The barrier-after-ALU gap is mostly a dependent-iadd throughput gap, not the barrier

Status: one device (M2 Max G14C), direct DRM, straight-line, simulator-gated (barriers swapped for same-length waits). 0 faults, no hang-budget use.
Looks at safe-02 item 3 (`barriercost` measured 1.57 us per round against the model's 0.60).

## Test

N = 1 / 33 / 65 back-to-back `threadgroup_barrier` (0x68), each preceded by A = 0 / 4 / 32 dependent `iadd`s, workgroups of 32 / 128 / 256 / 1,024 lanes,
131,072 lanes, 3 runs (144 dispatches incl. a control with the same iadds and no barriers). Cost per round = slope of firmware time against N.

## Result

* A dependent `iadd` costs **72-87 ns per 131,072 lanes** with no barrier at all (control). With 32 iadds a round takes 2.2-2.6 us whether or not a barrier
  follows (barrier extra -139 to +57 ns): the barrier hides behind the ALU work.
* With 4 iadds before it the barrier adds only **40-57 ns** per round (128 / 256 lanes). Back-to-back barriers (A = 0) cost 5-105 ns.
* **The cost model predicts 0.57-0.71 us for the 32-iadd round at 128 / 256 lanes against 2.2-2.6 us measured (3-4x low)**, and 0.06-0.08 us for the 4-iadd round
  against 0.34-0.39 us. The error sits in the dependent-iadd chain (model about 18-22 ns per iadd, hardware 72-87 ns), not in the barrier cost, which the model
  already treats as small. The `barriercost` shader's 1.57 vs 0.60 us gap is therefore likely the same ALU-chain shortfall; not re-run here (the workload
  verifier needs numpy).

Not done: fixing `cost.rs` (the chain rate may be specific to a dependent single-register chain; independent iadds are calibrated elsewhere), 1-32 SIMD groups with
mixed ALU, workgroups per core.

## Reproduce

`python3 scripts/run_drm_barrier_cost.py offline|hardware [--control]`; `make verify-barrier-cost` (offline, 5 checks against
[results/2026-10-18-barrier-cost](../../results/2026-10-18-barrier-cost)).

Later [ordinary arithmetic follow-up](../2026-10-20-integer-chain-cost/README.md):
1/2/4/8 interleaved chains all retain a similar isolated-dispatch timing
shortfall. This does not support assigning the entire gap to single-register
dependency latency. Clock/warm-up and program-length effects remain open;
consecutive repetitions are next. No global add-cost parameter was changed.
