# Stack (scratch) memory works through Mesa; exact binary captured; direct-DRM setup documented, not run

Status: confirmed on one device (driver-reported M2 Max G14C B1) through Mesa 25.1.9 GLES;
the direct-DRM reproduction was deliberately not attempted (see below).

## Claim and scope

A GLSL compute shader with a dynamically indexed 1,024-entry private `uint` array
(`tests/gles_compute.c` mode `private`) compiles to stack instructions, and Mesa's driver runs it
with **all 64 outputs exact**. The compiled main shader (198 bytes) was carved out of Mesa's
on-disk shader cache and decoded with applegpu ([disassembly](../../results/2026-10-11-stack-via-mesa/disassembly.txt)):

```text
b500c10520800004  stack_adjust #0x40c          (applegpu prints "stack_store i8, …, 1036")
b51a800400c01200  stack_store i32, x, r3 -> [stack + r4]   (r4 = index << 2: byte offset)
3512400400c01200  stack_load  r2 <- [stack + r2], slot 0
351a604400c01200  stack_load  r3 <- [stack + r3], slot 1   (two loads in flight, wait 0 / wait 1)
```

* **Size unit.** `stack_adjust` takes 32-bit words: Mesa emits
  `align(ceil(scratch_bytes / 4) + 10, 4)` = 1,036 for 4,096 bytes (`agx_compile.c:3417`).
  It is the first instruction of the main shader.
* **Addressing.** Stack loads/stores take a byte offset register; the compiler shifts the
  element index left by 2 with `iadd …, lsl 2`.
* **applegpu conflict.** `stack_adjust` shares opcode 0xb5 with `stack_store` and applegpu
  decodes it as an i8 store; a disassembler must special-case Mesa's fixed bits.
* Mesa declares 256 preamble registers for any shader with scratch (`nr_preamble_gprs`).

**Driver side (from Mesa source, not run over direct DRM).** The stack is backed by a scratch
buffer `agx_scratch.c` builds: a header with per-core block-list pointers, per-core arrays of
`agx_helper_block` for up to `AGX_MAX_SUBGROUPS_PER_CORE` = 128 subgroups (Mesa's FIXME guesses
"96 + 8"; the [occupancy finding](../2026-10-11-occupancy/README.md) measured 96), and blocks of
`32 lanes × 4 B × (8 << 2·log4)` words. A firmware-invoked **helper program** from Mesa's libagx
library hands out blocks at run time. The earlier hand-built helper attempts stalled (~0.5 s);
reproducing this path over direct DRM needs Mesa's helper binary and should only be tried when
a reboot is available.

Update 2026-10-18: register spills, vec4 and 16-bit stack accesses were captured and replayed in the simulator ([follow-up](../2026-10-18-stack-mesa/README.md)).

Not established: spilling of registers (as opposed to private arrays), `stack_get_ptr`,
`TODO.stack_adjust(2)`, `async_load/store`, negative stack_adjust at shader end, and preamble
scratch.

## Reproducer and evidence

`python3 scripts/run_gles_stack.py` (hardware, through Mesa), `python3 scripts/verify_stack_via_mesa.py`
(offline). Evidence: `results/2026-10-11-stack-via-mesa/`.

## Compiler implications (PTX)

* `.local` arrays and spills map onto stack_load/stack_store with byte offsets; emit Mesa's
  `stack_adjust` prologue with the word count formula above.
* The runtime must provide Mesa-equivalent scratch: until the helper-program path is reproduced,
  a ZLUDA backend should run through Mesa's driver (Gallium/Vulkan) for kernels that use local
  memory rather than raw DRM submission.
