# Direct-DRM differential SR scan evidence — 2026-10-11

Compact summaries (`scripts/extract_sr_scan.py`) of 35 `run_drm_sr_scan.py`
sessions. The raw records hold every selector for every lane (up to 1.2 GB) and
remain under `/scratch/apple-m2-playground/drm-compute/sr-scan/<utc>/record.json`.
Per configuration, a summary keeps the env overrides, lanes, oracle and
no-execution flags, firmware times, USC words, per-selector distinct values (top 4
with counts), per-SIMD-group values of SR7/17/19/20/21/32/53/113, and SR17
per-core slot statistics.

| Sessions (UTC) | Contents |
| --- | --- |
| 002042, 002048 | First base scan; 13 single-parameter configs |
| 002117 | Separation attempt; `words-only` refused by the harness (overlap) |
| 002132 | SR32 placements, local sizes 96..1024, repeated CDM moves |
| 002239, 002304 | USC word orders and preshader variants |
| 002348 | 2-D/3-D workgroup shapes and orders keeping the preshader word last |
| 002405 ×3 | `order-shru` / base repeats (SR17 and SR113 randomness) |
| 002422 | 2048 one-SIMD and 512 four-SIMD workgroups (SR17 separates from SR53) |
| 002449 | Register sweep without residency delay |
| 002639, 002651 | Register × workgroup-size sweep with a ~1 ms resident delay |

| 004603, 004701 | Preamble delivery control (constants via uniform_store) |
| 004612 | Preamble scans: selectors 0..127 and 128..255, 4-SIMD and 2048-workgroup shapes |
| 004715 | Preamble scans paired with main-shader SR20/17/0/24 (slots 250..253) |
| 004747 | Preamble run counter, non-atomic |
| 004911 | Device atomic add validation (33 / 64 / 65,536 lanes) |
| 004923 | Preamble run counter with atomic add |

| 011124..011125 (×6) | Strict-checked: base, Shader unk_2 = 2, imageblock 32×32 / 32×16 / 16×16 |
| 0111xx..0112xx (×8) | Strict-checked: sample stride 0..15, sample count 2 / 4 |

Session 004642 is omitted: a runner bug made the preamble scan the pairing slots
themselves (see notes/failed-approaches.md); its raw record stays in scratch.
`verification.json` is the output of `make verify-sr-direct`.
Report: [direct-DRM SR scan](../../experiments/registers/sr-direct-drm.md).
