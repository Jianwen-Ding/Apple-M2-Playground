# 2026-10-10 SR18/SR19 resource and get_sr width evidence

Extracted by `scripts/extract_sr_resources.py` from scratch runs. `manifest.json`
pins SHA256 of each file.

| File | Source command | Content |
| --- | --- | --- |
| `shared-full.json` | `run_agx_sr_shape.py --shapes 0 --shared-words 0,32,…,8192 --selectors all` | No-shared baseline: every lane of all 256 SRs. Other sizes: every lane of SR18/19 plus a SHA256 of each other selector's samples, for equality checks |
| `shared-granularity.json` | `… --shared-words 33,63,65,100,129,1000,4097,8000 --selectors 18,19,80` | SR18 granule |
| `meta.json` | `run_agx_sr_meta.py` | Raw record: export field values, SR18/SR19 sweeps, 7 single-field edits × 256 SRs, 2082 child runs |
| `width64.json` | `run_agx_sr_scan.py --preload 0x5a5a1234 --width 64 --selectors all --repeats 2 --count 65` | r3 after a 64-bit-destination get_sr, every lane |
| `width16.json` | `… --width 16 …` | r2 after a 16-bit get_sr, every lane |

`make verify-sr-resources` checks all of it against independent formulas. The
16-bit check uses `../2026-10-10-sr-shape-core/std-preload.json` as the 32-bit
reference. The self-test injects nine corruptions. Interpretation:
[report](../../experiments/registers/sr-resources-width.md).
