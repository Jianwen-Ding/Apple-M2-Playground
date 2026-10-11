# Threadgroup memory addressing: base is bytes, index counts 4-component slots

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Only decoded, Mesa-emitted instruction forms were used. This resolves the "usable threadgroup
memory = declared/4" observation in the [barrier finding](../2026-10-11-barrier-0x68-vs-0x78/README.md).

## Claim and scope

For `threadgroup_load` / `threadgroup_store` (`0x69` / `0x29`, 8-byte form, Mesa `agx_pack.c:769-792`):

**byte address = base + 4 × size(format) × index + size(format) × component**

* **base** (16-bit register, or immediate 0) is a plain **byte** address. Any 4-aligned value
  tested works (64, 100).
* **index** (16-bit register or immediate) counts **4-component slots**: 16 bytes for i32, 8 for
  i16, 4 for i8 (32/32 lanes for each format).
* **mask** selects components inside the slot: x, y, z, w at +0, +4, +8, +12 bytes for i32. A
  store with only y enabled takes its value from the **first** source register: enabled
  components consume consecutive registers starting at the named one.
* **The declared size is exact.** With USC Shared word
  `0x4d | 1<<8 | 0x24<<10 | (bytes/256)<<24`, base-addressed accesses work up to the last
  declared byte and fail at the first byte past it (2, 4 and 8 KiB, 18/18 cases). Out-of-range loads
  return 0, with no fault.

The earlier "declared/4" result came from addressing per-lane i32 elements with the
**index** operand. Each index step is 16 bytes, so 64 lanes × i32 really touched 1 KiB, not
256 B. Reinterpreted this way, all 23 earlier capacity cases fit exactly (touched bytes ≤ declared).

Mesa addresses shared memory only through the base register, with an immediate index of 0
(`agx_compile.c:1028-1054`, `agx_local_base` at `:978`). It never meets the index scaling.
That is consistent with these results.

## Reproducer and evidence

`scripts/run_drm_tg_layout.py` (hardware, a few seconds), `make test-tg-addressing`
([test](../../tests/test_tg_addressing.py); reruns the probe and checks it),
`make verify-tg-addressing` (14 offline checks).
[Evidence](../../results/2026-10-11-tg-memory-addressing/README.md).

Method: fill threadgroup memory with a sentinel through base addressing. Store per-lane tagged
values through the form under test, pass `threadgroup_barrier`, and read them back through base
addressing at candidate byte offsets. Only one mapping returns every lane's value.

## Compiler implications and limitations

* For CUDA `__shared__`, follow Mesa: put the byte offset in the base register, use index 0 and
  declare the real byte size. Use the index operand only for 16-byte-strided (vec4) access,
  e.g. one i32×4 slot per index. There it saves the address arithmetic.
* Shared-memory size needs no ×4 padding. The barrier stress harness declared 32 KiB for
  index-addressed data that touched exactly 32 KiB, so its results stand.
* Untested: signed or negative index immediates; the 6-byte short form; formats other than
  i8/i16/i32; multi-component masks with base addressing; the 64 KiB "field = 0" encoding.
