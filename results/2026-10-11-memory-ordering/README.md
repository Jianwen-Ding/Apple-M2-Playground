# Memory ordering evidence — 2026-10-11

`scripts/run_drm_litmus.py`, 65,536 lanes, 16 unrolled reads per lane; per variant: writer
fence, store policy (0 = Mesa u4 4, 1 = coherent u4 7), reader invalidate before the flag load,
reader fence between the loads. Each record has reads, flag-seen count, violations, the
same-core subset (SR20 per lane) and firmware time.

| File | Content |
| --- | --- |
| `matrix.json.gz` | writer none / f596 / Mesa queue-family × 2 store policies × 4 readers (1 repeat) |
| `bisect.json.gz` | 14 writer fences (each barrier alone and after f596), reader f59d before flag, 2 repeats |
| `reader.json.gz` | writer f533 / f596 × 2 store policies × 4 readers, 3 repeats |
| `nowait.json.gz` | both reader loads in flight before one wait; writers f533 / f596 / none, 3 repeats |

Offline: `scripts/verify_memory_ordering.py` (`make verify-memory-ordering`).
