# Task 1: hardware probing outline

## Milestones

| Step | Deliverable | Current state |
| --- | --- | --- |
| P0 | Repeatable environment capture, build, and DRM access check | Implemented; see baseline evidence in `results/` |
| P1 | Read-only Asahi parameter query and confirmed GPU identity | Complete for driver identity/topology; [G14C, 38 enabled mask bits](../experiments/baseline/device-params.md); product name is source interpretation |
| P2 | Minimal GPU compute submission with deterministic memory readback | Complete through Mesa GLES: [22 dispatches, 26 whole-buffer readbacks](../experiments/baseline/compute-readback.md); reviewed smoke command `make compute` |
| P3 | Execute a known AGX instruction sequence and compare against a host oracle | Proven narrow scope: [pinned G14C B1 move-immediate field](../experiments/arithmetic/first-agx-instruction.md), with guarded readback; other decoder labels remain hypotheses |
| P4 | Controlled instruction and operand variations with stored evidence | First one-bit immediate variation passed at counts 33/257; broader operand/register/ALU coverage pending |
| P5 | Timing probes with a validated time source and repeatable measurements | Driver GET_TIME baseline complete ([evidence](../experiments/timing/driver-time.md)); [GLES elapsed calibration failed](../experiments/timing/gles-timer-calibration.md); pairs, shader counter and ISA timing remain unvalidated |

## Probe areas

| Area | First questions | Folder |
| --- | --- | --- |
| Baseline | Which GPU/UAPI is exposed? Can we submit and read back a result? | `experiments/baseline/` |
| Timing | Which timestamp mechanisms are exposed? Is a shader-readable counter available? | `experiments/timing/` |
| Registers | Which widths, aliases, modifiers, and special-register reads are valid? | `experiments/registers/` |
| Memory | How do address calculation, alignment, waits, and atomics behave? | `experiments/memory/` |
| Arithmetic | What are the integer, float, conversion, and exceptional-value semantics? | `experiments/arithmetic/` |
| Control flow | How do masks, divergence, branches, barriers, and lane operations behave? | `experiments/control-flow/` |

The current user priority is actual AGX instruction execution. Timing was an
earlier request; its completed calibration evidence is retained, without further
capability queries or timer sweeps in this integration. A driver time query is not proof of an ISA clock
register, and host ioctl latency is not instruction latency.

## First follow-up work

1. Preserve the completed [parameter](../experiments/baseline/device-params.md)
   and [driver-time](../experiments/timing/driver-time.md) controls when building
   subsequent probes. See [reviewed progress](../notes/2026-10-04-probe-progress.md).
2. Preserve the completed [GLES compute/readback control](../experiments/baseline/compute-readback.md)
   and [backend inventory](../experiments/baseline/linux-compute-backend.md).
3. Preserve emitted native-code provenance and the
   [unchanged export/import](../experiments/baseline/vulkan-binary-roundtrip.md)
   control, which passes exact readback with the pinned Vulkan runtime. The completed pinned patcher changes one live
   move-immediate field; opaque layouts remain tied to the exact control/driver.
4. Next select the independently reviewed [index imadd addend site](../experiments/arithmetic/native-control-disassembly.md)
   for a separate one-field experiment with its exact cached/signed operands,
   modulo-2^32 oracle, guards and unchanged controls; that independent report is an offline review.
5. Add bounded instruction variations, then promote reproducible findings to
   `novel-results/` with regression tests.

The supplied applegpu toolset describes G13/M1. Treat its encodings and model
as hypotheses to check on the project device. The resource guide also contains
unverified claims and missing embedded formulas; trace claims to primary
sources before using them as an oracle.

P1 reports a command timestamp frequency of 1,000,000,000 Hz; command timestamp
writes and readback have not been exercised. GET_TIME advances near the host
raw-clock rate over two short paced runs, which establishes a driver query
baseline. P2 now has hardware execution and exact readback through Mesa-compiled
GLSL, plus Vulkan unchanged shader-object binary delivery. P3/P4 have one
controlled native move-immediate variation; no whole-ISA validation follows.
[Counter reconnaissance](../experiments/timing/shader-counter-candidates.md)
found no justified shader timer selector. Its source offset/disjoint concerns
require separate command-timing validation; no shader counter or ISA latency is claimed. The move field observation supports an existing encoding on G14C,
not a new opcode or architecture discovery. Selected backend/counter evidence is
versioned rather than depending only on scratch.
