# Gap bits of memory, control-flow and SR instructions

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute.

## Claim

applegpu leaves these bits unaccounted; single flips on hardware give:

| Instruction | Bits | Effect |
| --- | --- | --- |
| `device_load` (long form) | 31 | **Load disabled: the destination becomes 0** for GPU- or CPU-written memory, whatever `wait` slot follows. Not a register base, not threadgroup memory. With bits 30+31 the destination is 0 after `wait 3` and left unwritten after `wait 0`. Bit 30 alone (applegpu `g`, Mesa scoreboard bit 0) loads normally. |
| `device_store` | 31 | **Store dropped** (memory keeps its old value). Bit 30 stores normally. |
| `get_sr` | 22 | **Undefined result**: mostly 0, occasional stale values that differ between identical runs, for all 256 selectors. |
| `get_sr` | 23–25, 30–31 | none |
| `threadgroup_barrier` | 8–15 | none (single-SIMD-group workgroup) |
| `if_icmp`, `if_fcmp`, `while_icmp`, `else_icmp` | 46–47 | none (same exec mask / r0l) |
| `pop_exec` | 8 | none |
| `threadgroup_load` / `threadgroup_store` | 4, 7, 35, 40–47, 62–63 | none; bits 4 and 7 lie in the opcode byte, so 0x79/0x39/0xe9/0xa9 are aliases |
| `uniform_store` (preshader) | 30, 31, 48 | none (u20 still receives the value) |

**Fixed encodings applegpu lists as TODO** (run once each, in the describe body):

| Encoding | Result |
| --- | --- |
| `TODO.after_sampling1` (0x101c), `TODO.after_sampling2` (0x62cc), `TODO.unk0C00` (0x000c) | GPU timeout (3 s wait, firmware recovery) |
| `TODO.unk40C0` (0xc040, 6 bytes) | fast failure (no firmware timestamps) |
| `TODO.unk30C0`, `TODO.unkC0000000`, `TODO.unkE800` (= 0x68 with bit 7), `doorbell` (0x0028) | no register or length effect |
| 0x00000051 (`TODO.unk51`; applegpu now decodes it as `no_var`) | ends the SIMD group (no later store runs), like the "ends" opcodes |

Also measured: `uniform_store` from the **main** shader does not produce a readable uniform
(the read returns unrelated values); from the preshader it works. Mesa only emits it in the preamble.

## Relationship to existing knowledge

Mesa packs device_load/store bits 30–31 as a 2-bit `scoreboard` (`agx_pack.c:754`) and bit 48 as
format bit 3. Bit 30 behaves like a scoreboard bit; bit 31 does not: it disables the access.
Mesa never sets scoreboard ≥ 2 for device memory, so it never meets this.

## Compiler implications

* Keep device_load/store bit 31 clear. A disabled load still writes 0 to its destination, so
  a stray bit 31 makes loads silently return 0 rather than faulting.
* Only use `uniform_store` in the preshader.
* The other bits above can stay zero; none changes behaviour.

Not tested: `call`/`ret` (bits 7–8: a wrong target could hang the GPU), stack instructions,
`async_load`/`async_store`, texture/image and fragment-only instructions.
Reproduce: see [evidence](../../results/2026-10-11-mem-control-bitflip/README.md); verify with
`make verify-mem-control-bitflip`.
