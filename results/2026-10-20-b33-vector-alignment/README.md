# B33: alignment of 64- and 128-bit device and threadgroup accesses (2026-10-20)

Blocker B33 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: i32 `xy` and `xyzw` loads and stores
need only 4-byte alignment, in device and threadgroup memory, and match the plain byte-address model** (the one
`agx_run` and the Sail model use), including device vectors that cross a 64-byte line or a 4 KiB page. The backend
can enable the load/store vectorizer for 4-byte-aligned PTX `.f32` / `.b32` accesses.

32 lanes per case, each lane at a different element index; every program ran in `agx_run` first (same results).
0 faults. The vector store with a uniform base is the control's own `device_store` with only its mask, register,
base and index fields changed (`agx_asm` field edit); every other form is assembler output.

| Case (`b33.py`, `b33tg.py`) | Byte offsets of the 32 accesses | Byte-address model | Rounded-down model |
| --- | --- | --- | --- |
| device load xy / xyzw | 0, 4, 8, 12 mod 16 (8 lanes each) | **32 / 32**, **32 / 32** | 16, 8 (only the already aligned lanes) |
| device store xy / xyzw | same | **32 / 32**, **32 / 32** (64 / 128 words written, nothing else) | 16, 8 |
| device load / store xyzw across 64-byte lines (lanes 0-15, bytes 60..75 + 64k) and 4 KiB pages (lanes 16-31, bytes 4088..4103 + 4096k) | | **32 / 32**, **32 / 32** | 0 |
| threadgroup load xy / xyzw (4 KiB, base register in bytes) | 0, 4, 8, 12 mod 16 | **32 / 32**, **32 / 32** | 16, 8 |
| threadgroup store xy / xyzw | same | **32 / 32**, **32 / 32** | 16, 8 |

Not covered: i16 accesses at 2-byte alignment, 8-bit formats, and the cost difference between aligned and
unaligned vector accesses (the matrixMul tile's 16 -> 4 loads is the expected win).
