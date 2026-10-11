# Descriptions of the 49 non-faulting undecoded AGX opcodes

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.

The [direct-DRM scan](../../results/2026-10-11-opcode-scan-drm/README.md) found 49 opcode
values that applegpu cannot decode and that run without a GPU fault. It split them into 33
"no-ops" and 16 "ends". This finding describes each one: its instruction length, its
register effects, which lanes and groups it affects, the effect of operand bits, and its cost.
The 9 faulting opcodes (0x06 0x24 0x34 0x44 0x46 0x54 0x5c 0x64 0x74) and 0x6e were
**not run**.

## Claim and scope

Each opcode was tested in 8 operand encodings: `base` = `op | 2<<7 | 4<<9` (the scan form),
`zero`, `d6` (D=r6), `dt0`/`dt1`/`dt3`, `b15` (bit 15 set) and `hi` (bits 7–15 all set).

### Per-opcode description

| Opcodes | Length | What it does |
| --- | --- | --- |
| **0x03 0x07 0x0b 0x0f 0x13 0x17 0x1b 0x1f 0x23 0x27 0x2b 0x2f 0x33 0x37 0x3b 0x3f 0x43 0x47 0x4b 0x4f 0x53 0x57 0x5b 0x5f 0x63 0x67 0x6b 0x73 0x77 0x7b 0x7f** (all 31 undecoded opcodes with low bits `0b11`) | **6 bytes** in all 8 encodings | **True no-op.** No change to r0l or r1–r23 for any tested bits 7–15 or tested operand bytes 2–5 (`6240 3800`, `3800 6240`). In a loop, it takes exactly as long as a 6-byte `mov_imm` (within 1% in every run), i.e. it issues at full rate. The earlier scan's "no-op" class hid the length: it silently swallowed 4 bytes of `wait` padding. |
| **0x18, 0x78** | **2 bytes** | **Bit 7 clear** (`base`, `zero`, `d6`, `dt0`, `b15`): no register effect. Its loop takes 3.9–5.0× as long as a 6-byte `mov_imm` loop, and the cost drifts within a process, so this is **not a plain no-op**. It behaves like a synchronizing control instruction. **Bit 7 set** (0x98, 0xf8): ends execution exactly as the "ends" group below does. This mirrors the control family `xxxx1000`: `trap` 0x08 / `stop` 0x88, `wait` 0x38, `threadgroup_barrier` 0x68. |
| **0x01 0x0d 0x1d 0x2c 0x2d 0x3c 0x3d 0x4d 0x50 0x5d 0x60 0x6c 0x6d 0x70 0x7c 0x7d** | — (nothing after them runs) | **End the whole SIMD group, ignoring the exec mask.** The result is the same in all 8 encodings. Stores issued before them reach memory. No instruction after them runs, including the control's own `pop_exec`/`stop` suffix. The dispatch completes normally (no fault, normal firmware time). |

### Ending semantics compared with `stop` (0x88)

32-lane SIMD groups; "after" = a store placed after the instruction (and after the inner `pop_exec`):

| Variant | `wait` (reference) | `stop` | 16 ends opcodes, 0x98, 0xf8 |
| --- | --- | --- | --- |
| all lanes active | all continue | all end | all end |
| lanes 0–15 active, 16–31 masked | all continue | **only lanes 0–15 end**; 16–31 continue after `pop_exec` | **all 32 end** |
| no lane active (not jumped over) | all continue | **no effect** | **all 32 end** |
| jumped over with `jmp_exec_none` | all continue | all continue | all continue |
| run only in SIMD group 0 of a 2-group workgroup (64 lanes) | all continue | group 1 continues | group 1 continues |
| run only in workgroup 0 of two 32-lane workgroups | all continue | workgroup 1 continues | workgroup 1 continues |

So the ends opcodes act per SIMD group, not per lane, and never reach beyond their own
SIMD group. They act even when every lane is masked off. That matches the 2026-10-04
Vulkan note that they "also act when the group has no active lanes unless jumped over".

### Side finding: under-declared registers are silently corrupted

The first full run declared 32 register halves (`gprs 32` = r0–r15) while the probe used
r0–r26. In 4 of 894 dispatches, registers above r15 (the table index and stride) came back
wrong, so stores landed in the wrong slots or were lost. Those were **exactly the 4
dispatches with firmware time > 15 µs** (16.9–21.1 µs; every other dispatch was at most
14.9 µs). None reproduced in 5 reruns each, and one of them never executed the candidate
(it was jumped over). Declaring 64 halves gave **0 corrupted dispatches in 894**, although slow
dispatches still occurred. Using registers beyond the USC register count usually works, but
it is corrupted whenever the dispatch is disturbed, probably by preemption or a context
switch that saves only the declared registers. The count is in **16-bit halves** (Mesa
`max_reg + 1`; `AGX_NUM_REGS` = 256).

Not established: what 0x18/0x78 synchronize with; whether the 6-byte no-ops have
a meaning when other operand bytes are used; whether the ends opcodes differ from each
other in any way (e.g. in fragment shaders or with pending memory operations); and why
the "ends" form exists alongside `stop`.

## Reproducer and evidence

* `make opcode-describe`: full hardware suite (906 submissions + 37 timing loops;
  `CONFIRM_GPU_FAULTS=1`, refuses the faulting opcodes, stops at the first fault).
* `make test-opcode-describe`: hardware regression on a small subset ([test](../../tests/test_opcode_describe.py)).
* `make verify-opcode-describe`: 39 offline checks of the retained evidence.
* [Evidence and method](../../results/2026-10-11-opcode-describe/README.md).

Method: after the candidate come 8 markers `mov_imm r16l..r23l, 56`. Each is 4 bytes,
`62 xx 38 00`, and its upper half is itself `wait 0`, so a longer candidate can only
swallow whole markers or land on a `wait`. Two layouts (with and without one leading
`wait`) give the exact length. r2–r23 are preloaded with distinct values, and r0–r23
are stored after the candidate. The store index is recomputed from SR80, so a clobbered
register cannot redirect a store. Every result was compared with a reference body
(`wait` in place of the candidate) that matches its oracle exactly.

## Relationship to existing knowledge

Offline research delegated to OpenCode found **no name or encoding for any of these 49 values**
in Mesa (`AGX2.xml`, `agx_opcodes.py`), applegpu or the resources guide. Copilot's
analysis of the length rules gave bit 15 as the conventional length bit
(`AGX2.xml:7`, applegpu `length_bit_pos`). It *predicted* a 2-byte length for the
low-`0b11` class; hardware shows 6 bytes, with bit 15 having no effect on any of them. The
`xxxx1000` pattern for 0x18/0x78 comes from the known encodings of `trap` 0x08, `stop` 0x88,
`wait` 0x38 and `threadgroup_barrier` 0x68 (`agx_opcodes.py:322-405`).

## Compiler implications and limitations

* A compiler never needs these opcodes, but a **disassembler must treat the low-`0b11` class
  as 6 bytes**. Treating them as 2 bytes desynchronizes everything after them.
* The ends opcodes give a mask-independent "end this SIMD group" that `stop` does not.
  Mesa-generated code never uses it, so a PTX backend should keep using `stop`. The
  difference matters for code that exits inside divergent control flow: `stop` there
  ends only the active lanes.
* **Always declare at least `max_reg + 1` register halves.** An under-declared shader
  passes almost every test and still fails in roughly 0.5% of dispatches under load.
* Timing loops on this GPU must compare raw times from the same run. Subtracting an empty
  loop is not additive, and absolute loop times varied 2.2× between processes.
