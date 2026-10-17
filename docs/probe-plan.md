# Task 1: hardware probing outline

## Milestones

| Step | Deliverable | Current state |
| --- | --- | --- |
| P0 | Repeatable environment capture, build, and DRM access check | Implemented; see baseline evidence in `results/` |
| P1 | Read-only Asahi parameter query and confirmed GPU identity | Complete for driver identity/topology; [G14C, 38 enabled mask bits](../experiments/baseline/device-params.md); product name is source interpretation |
| P2 | Minimal GPU compute submission with deterministic memory readback | Complete through Mesa GLES: [22 dispatches, 26 whole-buffer readbacks](../experiments/baseline/compute-readback.md); reviewed smoke command `make compute` |
| P3 | Execute a known AGX instruction sequence and compare against a host oracle | Complete: direct-DRM submission with exact host oracles is the standard harness (`tests/drm_compute.c`) |
| P4 | Controlled instruction and operand variations with stored evidence | 131 of 159 applegpu descriptors mapped or classified ([coverage](isa-coverage.md)); ALU gap bits, sub-op spaces, atomics, float/int64 semantics, memory ordering in [novel results](../novel-results/README.md) |
| P5 | Timing probes with a validated time source and repeatable measurements | In-shader CPU clock, loop/ALU latency, load latency, occupancy (direct atomic counters) — see novel results |

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

## Status on 2026-10-11 (after the atomics/semantics session)

Done without GPU hangs (0 recovered timeouts this boot): device and threadgroup atomics (Mesa ops 0–10),
fp32/fp16 add/mul/fma semantics, 64-bit integer and pointer arithmetic, occupancy, cross-core memory
ordering, else/while_fcmp, and the stack path through Mesa. Deferred because they risk hangs and need a
reboot to be available: atomic ops 11–15 and u-bits, `call`/`ret`/`jmp_incomplete`/`jmp_if_skipping_doorbell`,
direct-DRM scratch (helper program), and the remaining unknown-opcode probes. The 28 open descriptors
are otherwise fragment-only or need texture/sampler state.

## First follow-up work (historical)

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

## Open safe probes (2026-10-16)

The next hang-free probes are written up as self-contained tasks in AGX-Performance-Simulator
[`tasks/safe-probes.md`](https://github.com/Jianwen-Ding/AGX-Performance-Simulator/blob/main/tasks/safe-probes.md):

- safe-01: exact `convert`, fp16 transcendental and subnormal semantics against PTX;
- safe-02: the largest cost-model gaps (atomic contention, strided access, barriers, write-back, the sin / cos cost);
- safe-03: memory-system parameters (line and page size, TLB reach, SLC capacity, CPU <-> GPU visibility latency);
- safe-04: driver and submission behaviour (priorities, concurrent queues, launch latency, multi-dispatch commands);
- safe-05: texture and image instructions through Mesa-compiled shaders;
- safe-06: recording the 214 coverage "may fault" special-register cases (each selector already read without fault).

Its "Not safe" list is the current do-not-run list.

## Remaining work (2026-10-17)

All open items, split into safe and owner-approval-only work, with a suggested order: [remaining-work.md](remaining-work.md).
