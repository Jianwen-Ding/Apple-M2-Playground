# Barrier gap-bit evidence (2026-10-20)

`record.json.gz`: `run_drm_barrier_bits.py` records. `n64` / `n128` / `n256` are uniform single-bit sweeps; `split-01` and
`split-all` are the split-workgroup barrier-ID tests. Per variant: mismatches, lanes with errors per SIMD group, firmware ms
and fault flags. Check: `make verify-barrier-bits`.
