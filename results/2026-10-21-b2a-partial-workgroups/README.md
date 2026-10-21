# B2a and B2c: partial workgroups and the "no threadgroup memory" Shared word (2026-10-21)

Blockers B2a and B2c of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM through
agx_runtime, battery power (no timing claims). 0 faults; hang budget unchanged (0/30).

## B2a: the hardware runs partial workgroups

**Result: the CDM global size does not have to be a multiple of the local size.** The dispatcher runs exactly
X x Y x Z threads, cutting the last workgroup short in every dimension, including grids smaller than one workgroup
and partial SIMD groups. `agx_runtime` does not need to reject non-multiples; CUDA grids are whole blocks anyway, so
nothing changes for ZLUDA, but Mesa-style ragged dispatches are fine.

`count.bin` (`build.py`, checked in `agx_run` first, which also models 100 threads for global 100 / local 32): the control
kernel with every lane atomically adding 1 to table word 0 and storing its x position at out[8 + gid]. `b2a_partial.rs`
(local agx_runtime example, not pushed to ZLUDA) builds the CDM stream by hand with any global / local size.

| Global (x, y, z) | Local | Counter (threads run) | Distinct x written |
| --- | --- | --- | --- |
| 96, 1, 1 (control) | 32 | 96 | 96 |
| 100, 1, 1 | 32 / 64 / 128 | 100 | 100 |
| 1, 1, 1 | 32 | 1 | 1 |
| 33, 1, 1 / 65, 1, 1 | 32 / 64 | 33 / 65 | 33 / 65 |
| 10, 1, 1 / 1000, 1, 1 / 1025, 1, 1 | 1024 | 10 / 1000 / 1025 | same |
| 40, 3, 1 | 32, 2, 1 | 120 | 40 |
| 32, 5, 1 | 32, 2, 1 | 160 | 32 |
| 32, 1, 5 | 32, 1, 4 | 160 | 32 |
| 7, 7, 7 | 4, 4, 4 | 343 | 7 |
| 50000, 1, 1 | 256 | 50000 | 50000 |

Every fence succeeded with valid timestamps; `wrong` (a written word other than its own gid) was 0 everywhere
(`runs.jsonl`).

## B2c: the "none" Shared word does not limit occupancy

**Result: answered by existing data.** With no threadgroup memory, agx_runtime emits `0x4d | 0x24 << 10` (bit 8 clear,
size field 0), exactly `drm_compute.c`'s default Shared word. The occupancy study
(`novel-results/2026-10-18-occupancy`, `run_drm_occupancy2.py`) ran its 0 KiB cells with that default and reached
**96 resident SIMD groups and about 55 workgroups per core**, the same as the register limit alone; B5's co-residency
runs used it too. Bit 8 is the "uses threadgroup memory" flag; with it clear the size field is ignored, so the
encoding is the correct "none", and kernels without threadgroup memory are not limited to one workgroup per core.
