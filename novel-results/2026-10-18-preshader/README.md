# Preshader follow-ups: the uniform count field sets a 32-uniform-per-group file, one preamble run per core per dispatch, and a preamble is nearly free

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. Follow-up to the
[preshader finding](../2026-10-11-preshader-execution/README.md). Preambles use only `uniform_store`, `mov_imm`, `get_sr`, ALU and the device
atomic add (no return) that earlier runs executed, always end with `stop`, no barriers; the uniform program was run in the Rust simulator first.
0 faults. (Hang-budget note: a run that the harness itself refused before any submission, a preamble too large for the USC layout, was
recorded as a failure by my wrapper by mistake, so the budget reads 4 of 30 instead of 3; the wrapper no longer does that.)

## 1. Uniform file size: set by the CDM launch word, 32 uniforms per group

`tests/drm_compute.c` now takes `AGX_UNIFORM_GROUPS` (CDM launch word 0, field `Uniform register count`, 3 bits, groups of 64 halves, default 1).
For each value 1..7 the preamble writes `u<U> = 0xC0DE0000 | U` (`uniform_store` to halves 2U, 2U + 1; immediate offsets reach u127, a register
offset the rest) for every uniform inside the allocation except the harness's own u4..u9, and the main shader copies u0..u255 into the table.

| Field | Uniforms allocated | Written uniforms read back |
| --- | --- | --- |
| 1 (default) | 32 | 26 of 26 |
| 2 / 3 / 4 / 5 / 6 | 64 / 96 / 128 / 160 / 192 | 58 / 90 / 122 / 154 / 186 of the same numbers |
| 7 | 224 | 102 of 102 (a sample: every 4th below u160 and all above) |

* **Capacity = 32 x field uniforms** (the field counts 64 halves). Everything written inside it reads back exactly, on every lane, in two runs.
* **No aliasing:** nothing beyond the allocation ever shows a written value, so high uniforms do not alias low ones.
* **Reads beyond the allocation return garbage:** arbitrary words (880 of 896 differ between two runs; 18 were 0 in the second run). The simulator's
  256-uniform file has no such notion; code must not read uniforms it did not allocate.
* A preamble cannot size the file; the dispatch must request it. **Field 0 (possibly 8 groups = 256) and writes beyond the allocation were not run**: a
  `uniform_store` past the file could hit memory outside it, so this stays unsafe without the owner's approval.

## 2. How often the preamble runs

A preamble adding 1 to `table[SR20]` (device atomic add, no return) over 65,536 lanes (2,048 workgroups):

* **Exactly once per core per dispatch on all 38 cores**, whether the dispatches are separate submits (1 submit: 1 run per core, 3 submits: 3) or several
  commands in one submit (`AGX_CMDS` = 2 or 4: 2 or 4 runs per core; 2 commands x 3 submits: 6). Totals were 38, 114, 76, 228, 152, 304.
* It is not once per command stream: every dispatch re-runs it, so uniforms from a previous dispatch are rewritten (a dispatch without a preamble was
  not tested, so whether stale uniforms survive into a preamble-less dispatch on the same core is still open).

## 3. Preamble registers and occupancy

* **SR19 (register allocation) is 64 and the peak occupancy is 96 groups at 16 declared halves / 52 groups at 64 halves, identical** with no preamble, a
  `stop` preamble and a preamble writing r2..r30 (declared 64 halves = r0..r31).
* A preamble using more registers than the declared main-shader count was **not run** (it could overrun its allocation); the harness has no separate
  preamble register field.

## 4. Cost

2,048 workgroups, null main, clock keeper running, 15 interleaved samples (median firmware ns):

| Preamble | Dispatch time | vs none |
| --- | --- | --- |
| none | 9,583 | |
| `stop` only | 9,500 | -83 (noise) |
| 64 dependent ALU instructions | 9,834 | **+251** |
| 256 dependent ALU instructions | 12,416 | **+2,833** |

* A preamble is effectively free up to a few dozen instructions; 256 dependent instructions cost about 2.8 us per dispatch (about 11 ns each, the single-lane
  dependent-ALU latency, once per core in parallel).

## For PTX

Hoist kernel-uniform values (argument pointers, `blockDim` products, constants) into the preamble; request `32 x ceil(n / 32)` uniforms in the launch
(up to 224), never read beyond them; budget a few dozen preamble instructions per dispatch at no measurable cost.

Not established: field 0 / writes beyond the file, uniforms surviving a preamble-less dispatch, preamble registers beyond the declared count, and the
coverage case (`MANUAL preshader`).

## Reproduce

`python3 scripts/run_drm_preshader.py offline|uniforms|count|regs|cost`; `make verify-preshader` (offline: 15 checks against
[results/2026-10-18-preshader](../../results/2026-10-18-preshader); `--no-sim` skips the simulator replay).
