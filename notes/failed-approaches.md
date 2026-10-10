# Failed approaches and known limitations

| Date | Approach or check | Actual observation | Next action |
| --- | --- | --- | --- |
| 2026-10-04 | Discover libdrm through `pkg-config --modversion libdrm` | Package metadata was unavailable | Initial smoke test uses installed DRM headers and direct ioctl calls |
| 2026-10-04 | Reuse supplied applegpu hardware harness on Linux | Inspection found `xcrun` and Metal framework dependencies; execution was not attempted | Build a separate Linux/DRM execution backend; reuse offline tools as appropriate |
| 2026-10-04 | Identify board through `/proc/device-tree/model` and `compatible` | Both paths absent in the container | [Parameters now report G14C](../experiments/baseline/device-params.md); exact board and memory capacity remain unmeasured |
| 2026-10-04 | Discover Vulkan/OpenCL tooling on `PATH` | `vulkaninfo`, `clinfo`, `glslangValidator`, and `spirv-as` were not found | Inventory libraries before choosing a compute backend; tool absence alone does not prove API absence |

The DRM version smoke test has passed. No failed GPU shader submissions or
instruction probes have been observed yet. Add such failures with their inputs,
return codes, logs, and control result when they occur.

## Reviewed read-only probe failures

[Params evidence](../results/2026-10-04-device-params/README.md) retains missing
node (`ENOENT`), `/dev/null` version rejection (`ENOTTY`), wrong driver `apple`,
missing compiler, and invalid usage. The integration rerun repeated a missing
node failure. No unsupported GET_PARAMS or malformed kernel response was induced.

[Time evidence](../results/2026-10-04-driver-time/README.md) retains a missing
node and invalid argument bounds. Integration repeated `/dev/null` rejection
before GET_TIME. No unsupported GET_TIME, reset, or GPU submission was attempted.

Review found that the original time runner could accept zero or too few samples
and could crash on malformed JSON without a summary. The corrected runner
requires exact successful counts and validates metadata/sample fields before
analysis. [Synthetic regression evidence](../results/2026-10-04-driver-time/integration-review/verification.json)
shows malformed/empty/truncated data, failed records, invalid types, duplicate
indices, nonzero flags, invalid host brackets, backward time, and stalled time
all produce status 1 with `passed: false`. These are software failure injections,
not observed hardware faults. Available timeout output is retained; timeout and
permission failure paths were not induced in this review.

During final integration, another owner added a GLES C probe. The expanded default
`make check` failed on missing system `EGL/egl.h`. Supplying the unchanged Mesa
header include root via `CC='cc -I/save/workspace/AGX_Probe/mesa/include'` let all
four current C files pass syntax checking. That probe was outside the first integration commit. The subsequent P2 review
adds `PROBE_INCLUDE` to shared tooling so normal `make check` can use vendor
EGL/GLES/Vulkan headers without embedding include flags in `CC`.

## P2 and backend review

[P2](../experiments/baseline/compute-readback.md) now demonstrates actual GLES
compute/readback. Its stored wrong-oracle, invalid-GLSL, wrong-device, missing-
header/device, and host-only timeout/launch failures are selected evidence.
The original runner hardcoded `cc`; integration now honors `CC`. A missing
compiler override failed before API children, with a retained summary.

[Backend inventory](../results/2026-10-04-backend-inventory/README.md) records
historical Vulkan ICD loading failure due to `libdisplay-info.so.2`; this review
does not rerun or integrate the ongoing Vulkan owner's runtime work.
[Counter research](../results/2026-10-04-shader-counter-research/README.md)
found no justified shader timer selector. Inspected source writes both compute
timestamp destinations to `comp_start` and returns constant-zero disjoint state.
These predict timing hazards if present in the installed build; this review
measured neither broken command timestamps nor instruction latency.

## Multiply-add probe and delegation limitations

The pinned [imadd addend test](../experiments/arithmetic/imadd-addend.md) passed;
there was no observed GPU/import/oracle failure for the refreshed native patch.
The intentionally stale digest was rejected before dispatch. This supports the
pinned wrapper integrity behavior only. General addend carry, register coverage
and instruction timing remain untested.

This session's acm-dev native Claude/Grok CLI launches failed, and native Gemini
workers required authentication. OpenCode-backed Kimi K3 and GLM 5.3 performed
implementation/hardware and offline review respectively, but stopped during final
packaging on provider access/funding errors. Their code and passing raw evidence
were recovered; coordinator integration completed the reproducible artifacts.
Do not interpret a running process or provider failure as a completed review.

### Special-register scan, 2026-10-04

The full 0..255 sweep and separated paired reads found no progressing shader
clock through the tested 32-bit `get_sr` path. SR32 changes between fresh command
buffers, with the same 0x24000 step at counts 1, 33, 65, and 257; this is not a
workgroup-count or elapsed-time oracle. Its underlying cause remains unidentified.
Two local patch validations failed before a mutated shader submission: the main
metadata includes 16 padding bytes (70 total, rather than 54 executable bytes),
and a textual conditional-disassembly comparison was too brittle. Both failures
are retained with the successful original controls. Known `wait 0` padding was
used because the reference decoder supplied no established nop encoding.
Paid ACM workers failed on provider funding; explicit Copilot model names were
unavailable. The configured default Copilot worker completed three review turns
and contributed the independent verifier. See the
[hardware report](../experiments/registers/special-register-scan.md).

### SR geometry / bit-15 follow-up, 2026-10-10

* `/scratch/apple-m2-playground` was root-owned and not writable by the probe
  user (uid 1000) this session. Default runner outputs failed with `PermissionError`
  before any GPU work. Pass `--output` / `SCRATCH_ROOT=` to a writable directory.
  `make check` also needs `SCRATCH_ROOT` overridden in that case.
* The bit-15 `get_sr` form (applegpu `TODO.sr_thing`) is **not** an alternate
  read or a move-to-SR in compute. Without a preload it stores stale
  register-file contents, which can look like random data. Always preload the
  destination when testing a possibly non-writing instruction.
* SR15/19/24/25/97/114 do not depend on workgroup shape or count. Small
  shapes produce coincidental matches (e.g. `gx = 2` for SR24), so fit formulas
  across several shapes before naming a register.
* No GLSL/SPIR-V compiler is installed (no glslang/glslc/spirv-as). SPIR-V is
  hand-encoded from the Mesa grammar and validated with libSPIRV-Tools.
* A shader that routes data through threadgroup memory reads back 0 when its
  shared allocation is edited to 0. Threadgroup stores/loads then silently do
  nothing, with no fault. This was briefly mis-read as "SR19 = 0".
* Editing exported `main_offset` (0x849) makes the shader write nothing. It is not
  a tunable field.
* 64-bit / 16-bit `get_sr` destinations expose no hidden clock half. `get_sr` is
  32-bit only, and SR113 is intermittent (0/8) and must not be attributed to an edit.

### Undecoded-opcode execution, 2026-10-10 — SYSTEM-VISIBLE GPU FAULTS

`scripts/run_agx_opcode_scan.py` executes the 59 low-7-bit opcode values the
applegpu model cannot decode. Nine of them (0x06, 0x24, 0x34, 0x44, 0x46, 0x54,
0x5c, 0x64, 0x74), executed by even one lane, discard every store of the whole
dispatch. The submitting process sees **no error**: the fence signals and a second
submission on the same VkDevice succeeds. **The project owner saw purple flashes
and desktop stutter while these ran.** These are almost certainly whole-GPU fault
recovery events that the shared display also experiences. Do not interpret "no
VkResult error" as "no fault".

* Run these only with the owner's agreement, on an idle machine. Keep counts
  minimal and capture `dmesg` (needs root) around runs. `make opcode-scan` is
  gated by `CONFIRM_GPU_FAULTS=1`.
* Repeated firmware faults on Asahi can require a reboot. Note that risk before any rerun.
* Results so far are in scratch only and are not yet a retained finding. Class A
  (17 opcodes) end the executing SIMD group, and also act when the group has no
  active lanes unless jumped over. 0x18-like opcodes are no-ops. Some 0x6e operand
  forms return stale, bit-noisy on-chip data. That resembles the LeftoverLocals
  class (CVE-2023-4969) and was deliberately not pursued.

### Command timestamps and direct DRM, 2026-10-10

* **`Write; Dispatch; Write` timestamps measure nothing on Honeykrisp.** Both land
  on stream ends, and the first one marks the end of the dispatch. This was first
  read as "compute timestamps are broken". Record top-of-pipe plus a second stamp
  before the dispatch, or use direct DRM's start/end pair.
* **Clock state looked like code-size dependence.** iadd chains at 65536 seemed
  cheaper per instruction than at 32768. That was a mid-run clock-state switch, not
  layout. Always print per-sample times. A 1.5–1.7× jump between consecutive
  identical dispatches is a state change.
* **Unrolled code cannot measure ALU latency.** Dependent and independent chains
  cost the same because instruction fetch dominates (~1.84 ns/byte). Use small
  loops.
* **A quick oracle with hard-coded word offsets mis-reported a failure** (tail at
  word 72 instead of 80). Compute the whole expected buffer from count and layout,
  as `run_drm_compute.py` does.
* **Host time is not a timing source.** Identical empty DRM dispatches took 115 or
  577 µs host-side. Firmware timestamps stayed at 5.7–7 µs.
* The opcode-scan kernel log was captured after the fact, and that session's scan
  outputs were lost. Its 286 timeouts / 73 Unmapped read faults cannot be matched
  to opcodes. See [kernel log evidence](../results/2026-10-10-opcode-scan-kernel-log/README.md).
