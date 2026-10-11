# AGX cycle cost model (moved)

The cycle cost model (`agx_cost.py`), its calibration and validation scripts (`cost_hw.py`,
`cost_probes.py`, `verify_cost_model.py`, `fetch_probe*.py`, ...) and this finding's full write-up
now live in [AGX-Performance-Simulator](https://github.com/Jianwen-Ding/AGX-Performance-Simulator), together with a bit-identical Rust port.

The hardware measurements it was fitted and validated on stay here as evidence in
[`results/2026-10-11-cost-model/`](../../results/2026-10-11-cost-model/) (also copied to the
simulator repository); the hardware findings derived from them are listed in
[novel-results/README.md](../README.md).
