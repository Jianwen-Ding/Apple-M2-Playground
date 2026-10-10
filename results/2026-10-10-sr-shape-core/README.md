# 2026-10-10 SR geometry, core-id and bit-15 form evidence

Compact per-lane evidence extracted by `scripts/extract_sr_shape_core.py` from
scratch runs. Raw records were 154 MB, mostly readback hex and the 65,536-lane run.
Every value used by the verifier is retained. Readback hex, API logs and scratch
paths were dropped. `manifest.json` pins SHA256 of each file.

| File | Source command | Content |
| --- | --- | --- |
| `shape.json` | `run_agx_sr_shape.py` (defaults) | 9 shapes × 29 selectors × 2 samples, every lane; patch site/bytes/decode; export SHA256; 550 child runs, all exit 0 |
| `core-id.json` | `run_agx_sr_scan.py --count 65536 --repeats 3` (20 selectors) | SR20/SR0 one value per workgroup plus per-workgroup uniformity; histograms for others (SR80: distinct/min/max/identity) |
| `alt-preload.json` | `run_agx_sr_scan.py --alt --preload 0xdeadbeef --selectors all --repeats 2 --count 65` | bit-15 form, every lane, all 256 selectors |
| `alt-reread.json` | `… --alt --reread --preload 0x5a5a1234 …` | bit-15 form followed by standard read |
| `std-preload.json` | `… --preload 0x5a5a1234 …` (no `--alt`) | standard-read baseline for the same body shape |

Each scan file also keeps control names and their unique values, including the
`preload-control` that must store the preload exactly.

Verify offline: `make verify-sr-shape` (no GPU). The self-test injects nine
corruptions (wrong SR7, lane swap, changed constants, extra core id, non-uniform
SR20, bit-15 destination write, bit-15 SR change, missing selector) and requires
each to be rejected.

Not retained: the stale-register smoke run (bit-15 form without preload) and the
small smoke runs, which were superseded by the full sweeps above. See the
[report](../../experiments/registers/sr-geometry-core-alt.md) for interpretation and limits.
