# Task 1: hardware probing outline

## Milestones

| Step | Deliverable | Current state |
| --- | --- | --- |
| P0 | Repeatable environment capture, build, and DRM access check | DRM check passed; runner being established |
| P1 | Read-only Asahi parameter query and confirmed GPU identity | Planned |
| P2 | Minimal GPU compute submission with deterministic memory readback | Planned; Linux execution backend needed |
| P3 | Execute a known AGX instruction sequence and compare against a host oracle | Planned; depends on P2 |
| P4 | Controlled instruction and operand variations with stored evidence | Planned; depends on P3 |
| P5 | Timing probes with a validated time source and repeatable measurements | Planned; priority request |

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

1. Query Asahi device parameters with the installed UAPI; retain header hashes
   and the raw output, including unsupported-ioctl errors.
2. Choose a Linux execution path after checking installed Mesa and compute
   facilities. Define buffer allocation, submission, completion, and readback.
3. Validate a constant-write kernel against an exact expected buffer before
   changing shader bytes.
4. Establish an unchanged control shader and a host oracle for each experiment.
5. Add bounded instruction variations, then promote reproducible findings to
   `novel-results/` with regression tests.

The supplied applegpu toolset describes G13/M1. Treat its encodings and model
as hypotheses to check on the project device. The resource guide also contains
unverified claims and missing embedded formulas; trace claims to primary
sources before using them as an oracle.
