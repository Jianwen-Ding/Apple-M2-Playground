# Memory / control / SR gap-bit runs — 2026-10-11

`scripts/run_drm_bitflip.py` (raw candidates), checked offline by
`scripts/verify_mem_control_bitflip.py` (11 checks, `make verify-mem-control-bitflip`).

| File | What |
| --- | --- |
| `misc1` | get_sr (22–25, 30–31), threadgroup_barrier (8–15), device_load (31) gap flips |
| `dld-regbase`, `dld-tg`, `dld-b31cpu`, `dld-sb2` | device_load bit 31: register base? threadgroup memory? CPU-written memory; scoreboard / wait slots |
| `dst-b31` | device_store bits 30/31 (table slot 0) |
| `gsr-b22`, `gsr-b22-rep1..3` | all 256 SR selectors with/without get_sr bit 22; determinism |
| `cf-gaps` | if_icmp/if_fcmp/while_icmp/else_icmp bits 46–47, pop_exec bit 8 inside if/mov/pop structures |
| `tg-gaps` | threadgroup_store/load gap bits in a store → barrier → load round trip (4 KiB shared) |
| `ustore-pre-*` | uniform_store in the preshader with bits 30, 31, 48; main reads u20 |
| `todo-fixed` | 9 fixed TODO encodings from applegpu (jmp_if_skipping_doorbell not run) |
