# Float semantics evidence — 2026-10-11

`scripts/run_drm_float.py` on direct DRM, 64 lanes per dispatch, one repeat; each lane loads
A, B, C from table words lane, 64+lane, 128+lane and stores the op result.
`float-all.json.gz` holds, per instruction, every (A, B, C, result) quadruple (`raw`), the
mismatch count of every model, and NaN output patterns. Offline: `scripts/verify_float_semantics.py`.

Model key: `daz` = denormal inputs flushed; `ftz1` = flush after rounding; `ftz2` = flush when
the exact result is below the smallest normal; `fused0/1` = fma rounded twice / once.
