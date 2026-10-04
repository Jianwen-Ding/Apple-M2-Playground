# Task 1: hardware probing outline

## Milestones

| Step | Deliverable | Current state |
| --- | --- | --- |
| P0 | Repeatable environment capture, build, and DRM access check | Implemented; see baseline evidence in `results/` |
| P1 | Read-only Asahi parameter query and confirmed GPU identity | Complete for driver identity/topology; [G14C, 38 enabled mask bits](../experiments/baseline/device-params.md); product name is source interpretation |
| P2 | Minimal GPU compute submission with deterministic memory readback | Complete through Mesa GLES: [22 dispatches, 26 whole-buffer readbacks](../experiments/baseline/compute-readback.md); reviewed smoke command `make compute` |
| P3 | Execute a known AGX instruction sequence and compare against a host oracle | Planned; depends on P2 |
| P4 | Controlled instruction and operand variations with stored evidence | Planned; depends on P3 |
| P5 | Timing probes with a validated time source and repeatable measurements | Driver GET_TIME baseline complete ([evidence](../experiments/timing/driver-time.md)); shader counter and ISA timing remain unvalidated |

## Probe areas

| Area | First questions | Folder |
| --- | --- | --- |
| Baseline | Which GPU/UAPI is exposed? Can we submit and read back a result? | `experiments/baseline/` |
| Timing | Which timestamp mechanisms are exposed? Is a shader-readable counter available? | `experiments/timing/` |
| Registers | Which widths, aliases, modifiers, and special-register reads are valid? | `experiments/registers/` |
| Memory | How do address calculation, alignment, waits, and atomics behave? | `experiments/memory/` |
| Arithmetic | What are the integer, float, conversion, and exceptional-value semantics? | `experiments/arithmetic/` |
| Control flow | How do masks, divergence, branches, barriers, and lane operations behave? | `experiments/control-flow/` |

Timing is the explicit request in the supplied `AGX_Probe/REQUESTS.md`. Start
by inventorying documented driver timestamp support, then develop a hypothesis
about shader-readable time. A driver time query is not proof of an ISA clock
register, and host ioctl latency is not instruction latency.

## First follow-up work

1. Preserve the completed [parameter](../experiments/baseline/device-params.md)
   and [driver-time](../experiments/timing/driver-time.md) controls when building
   subsequent probes. See [reviewed progress](../notes/2026-10-04-probe-progress.md).
2. Preserve the completed [GLES compute/readback control](../experiments/baseline/compute-readback.md)
   and [backend inventory](../experiments/baseline/linux-compute-backend.md).
3. Obtain emitted native-code provenance and validate an unchanged binary round
   trip before controlled raw AGX changes; the installed Vulkan path is separately
   owned and still outside this review.
4. Establish an unchanged control shader and a host oracle for each experiment.
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
GLSL. P3/P4 still need a known native sequence and controlled instruction changes.
[Counter reconnaissance](../experiments/timing/shader-counter-candidates.md)
found no justified shader timer selector. Its source offset/disjoint concerns
require separate command-timing validation; no shader counter, ISA latency,
or raw instruction execution is claimed. Selected backend/counter evidence is
versioned rather than depending only on scratch.
