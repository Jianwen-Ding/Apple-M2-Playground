# Stack encodings from Mesa: register spills use immediate offsets, arrays use a byte-offset register, and vec4 / 16-bit forms exist

Status: confirmed on one device (driver-reported M2 Max G14C B1) through Mesa 25.1.9 GLES. Follow-up to the
[stack-via-mesa finding](../2026-10-11-stack-via-mesa/README.md), which captured one private-array shader. Nothing is hand-built: Mesa's
driver sets up scratch and the helper program itself (no direct-DRM scratch, no hang risk). 0 faults.

## Test

Five GLSL ES 3.2 compute shaders (`scripts/run_gles_stack2.py`, `tests/gles_compute.c` with `GLES_SHADER_FILE`) run through Mesa on the GPU
with 64 lanes; every output equals a host model and the guard words are intact in all five. The AGX binary of each is captured from the
Mesa shader cache (`scripts/agx_capture.py`) and decoded with the Rust decoder (every region ends on an exact instruction boundary).

| Shader | What it stresses | Mesa stack use |
| --- | --- | --- |
| `spill` | 192 dependent `uint` values live to the end, no arrays | **70 spills and 70 fills**, `stack_adjust #80`, all 255 registers in use |
| `priv_u` | 1,024-entry dynamically indexed `uint` array | `stack_adjust #1036`; `stack_store` / `stack_load` i32 x |
| `priv_v4` | 64-entry `uvec4` array | `stack_adjust #268`; **i32 xyzw** (128-bit `r4_r5_r6_r7`) store and loads |
| `priv_f` | 512-entry `float` array | `stack_adjust #524`; i32 x |
| `priv_h` | 512-entry `mediump float` array | `stack_adjust #524`; **i16 x** (Mesa lowers mediump to 16 bits; the stack stride stays 4 bytes) |

## Encodings (from the captured code)

```text
stack_adjust #<words>                               first instruction of the main shader (applegpu prints it as a stack_store i8)
stack_store i32, 1, 0, x, 4, rD, <imm byte offset>, s   register spill: immediate offsets 0, 4, 8, ... 276 (70 slots); scoreboard s = 0 or 1
stack_load  rD, i32, 1, 0, x, 4, <imm byte offset>, s   the matching fill, same offsets
stack_store i32, 1, 0, x,    4, rD, rOff, 0         private array element: byte offset in a register (index << 2)
stack_store i32, 1, 0, xyzw, 4, rD_rD+1_rD+2_rD+3, rOff, 0     vec4 element, 128 bits
stack_store i16, 1, 0, x,    4, rDl|h, rOff, 0      16-bit element
```

* **`stack_adjust` words = align(ceil(scratch_bytes / 4) + 10, 4)** for all five shaders (80, 1,036, 268, 524, 524), matching the earlier formula.
* **Spills use immediate byte offsets, one 4-byte slot per spilled value (slot k at byte 4k); array accesses use an offset register.** A spill
  needs no address arithmetic.
* **The simulator already implements all of these** (per-lane stack memory). Replaying each shader's preamble and main in `agx_run` produces
  **exactly the hardware output word for word** for all five, with the uniform convention reconstructed from the captured code: `u0_u1` =
  a root table whose first word is `count` (the preamble loads it into `u4`), `u2_u3` = the output buffer, the rodata words at
  `u<base_uniform / 2>`. That validates the stack model on real Mesa code including 70 spills and fills under 255 live registers.

For PTX: `.local` arrays and register spills map directly onto these forms; a ZLUDA backend can emit `stack_adjust` + spill / fill with immediate
offsets and indexed `stack_load/store` with a byte-offset register, as long as the runtime provides Mesa's scratch buffer and helper program
(through Mesa's driver). The direct-DRM scratch path is still not reproduced.

Not established: `stack_get_ptr`, `TODO.stack_adjust(2)`, `async_load` / `async_store` (Mesa did not emit them for these shaders), 8-bit stack
accesses, a negative `stack_adjust` at shader end, preamble scratch, and the cost of a spill (the cost model has the instructions but no
measured latency for them).

## Reproduce

`python3 scripts/run_gles_stack2.py` (hardware, through Mesa; captures need `scripts/agx_capture.py --cache DIR` per shader),
`python3 scripts/replay_mesa_stack.py` (offline simulator replay), `make verify-stack-mesa` (offline, 20 checks against
[results/2026-10-18-stack-mesa](../../results/2026-10-18-stack-mesa); `--no-sim` skips the replay).
