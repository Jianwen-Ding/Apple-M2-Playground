# Threadgroup memory addressing runs — 2026-10-11

| File | Producer | Contents |
| --- | --- | --- |
| `layout.json` | `scripts/run_drm_tg_layout.py` | `stride`: index-form stores read back through byte offsets size·i and 4·size·i (i32/i16/i8). `mask`: single-component stores x/y/z/w read at 16i+0..12. `combined`: base 64/100 + index. `capacity`: base-addressed exchange at offsets up to and past 2/4/8 KiB declared. |
| `index-capacity.json` | `scripts/run_drm_tg_capacity.py` | The earlier index-addressed capacity probe (copied from the barrier results), reinterpreted with the 16-byte index stride |

`scripts/verify_tg_addressing.py` runs 14 checks (13 when pointed at a fresh run without `index-capacity.json`).
