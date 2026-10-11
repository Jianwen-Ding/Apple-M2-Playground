# 64-bit integer evidence — 2026-10-11

`int64-all.json.gz`: `scripts/run_drm_int64.py`, 12 forms × 446 input sets; `raw` rows are
(r6, r7, r8, r9, result low, result high). Inputs come from table regions 0–3, the high result
word is stored to region 4.

`pointer.json.gz`: `scripts/run_drm_pointer.py`; the u8/u9 read-back against the printed
table VA, then three register-base loads over table T[w] = 7w + 3.

Offline: `scripts/verify_int64.py` (`make verify-int64`).
