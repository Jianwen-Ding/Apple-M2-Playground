# Instruction-cache evidence (2026-10-20)

`record.json.gz`: `probe_icache.py` records. `dense-p0` / `dense-p2` are 8-byte scans; `padsweep/` holds loop-start
offsets; `straddle/` instruction sizes and offsets; `r16/` 16-repeat sharing, same-code and partial-shift runs; `occ/` 2-16
groups per core; `keeper/` early runs made with the clock keeper (coarse curve, streaming cost and bandwidth only, since
the keeper can share the probe's core). Each row has the per-repeat firmware ns, the oracle check and SR20 per group.
Check: `make verify-icache`.
