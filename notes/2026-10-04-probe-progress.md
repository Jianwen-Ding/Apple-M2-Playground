# Task 1 progress — 2026-10-04 integration reviews

Canonical source is `/save/workspace/apple-documentation-playground`; scratch
contains regenerable runs only. Reviewed the completed params/time C probes,
runners, reports, raw evidence, and provenance. Vendor Mesa/applegpu sources
were not modified. The first params/time review left the separately owned backend report untouched.
The follow-up review below integrates the subsequently completed P2/backend/
counter reports and selected evidence.

## Findings and milestone status

- P0: environment/build/DRM access baseline implemented.
- P1: three repeated driver parameter outputs report generation 14, variant C,
  revision `0x11`, chip ID `0x6021`. Cluster masks imply 38 enabled cores across
  40 logical slots. Local Mesa naming interprets this as M2 Max / G14C B1;
  this is source interpretation, not an independent shader or board measurement.
  The supplied 64 GB memory capacity remains unmeasured.
- Driver time baseline: all 264 GET_TIME queries succeeded in the reviewed rerun,
  with zero backward/equal steps. Two paced midpoint ratios were
  1.000000557 and 1.000000196 returned ns per host raw-clock ns; respective
  brackets [0.999997968, 1.000003146] and [0.999997699, 1.000002694] include 1.
  GET_TIME is a driver query; it does not establish an AGX shader clock register.
  Source review found the retained 24 MHz configuration excerpt is T6022/G14D,
  while P1 reports T6021/G14C. The report now makes that mismatch explicit;
  the lattice compatibility does not prove this device's physical timer frequency.
- P2 is now complete through Mesa GLES compute/readback (follow-up below).
  P3/P4 remain pending; P5 has a driver baseline only. Raw instruction execution,
  ISA latency and shader-counter semantics remain unestablished.

Primary reports and retained evidence:
[parameters](../experiments/baseline/device-params.md),
[time](../experiments/timing/driver-time.md),
[params review](../results/2026-10-04-device-params/integration-review/verification.json),
[time rerun](../results/2026-10-04-driver-time/integration-review/hardware/summary.json).
Original source/header hashes remain historical; reruns record reviewed code.

## First review: params/time changes and verification

Added `make params` / `make time` and matching shared runner commands. `make check`
now parses all current script Python files and syntax-checks all current C probes
using C11 and warnings as errors. It passed for smoke/params/time after the
initial code changes; the final numeric range guard was exercised by synthetic
checks and the final time rerun. A concurrent owner then added `gles_compute.c`:
default `make check` correctly failed on missing system EGL headers. All four
current probes passed with
`make check CC='cc -I/save/workspace/AGX_Probe/mesa/include'`, reading unchanged
vendor headers. This is syntax verification only; the GLES file remains outside
the first integration commit. Selected check summaries are retained alongside the
integration evidence. Shared command logging retains partial output on timeout.

Corrected time runner false-PASS paths: each phase must contain exactly its
requested successful count, matching metadata, sequential indices, integer
fields, zero flags/errno, valid host brackets, positive elapsed time, and no
backward timestamps. Malformed JSON yields a failed summary. Equal steps are
reported; PASS does not enforce a statistical rate threshold. C time probe now
fails on non-EINTR sleep errors or failed close. Params runner also requires
its successful probe output marker rather than accepting empty status-0 output.

Bounded `make params` (3 queries) passed; every stdout matched the original P1
output byte for byte. Original params evidence manifest hashes verified. Bounded
`make time` (8/128/64/64 queries, two 10 ms paced phases) passed; original time
raw data also passed the corrected validator. Each query phase had a 10-second
runner timeout; compile limits are 60 seconds.

Params missing-device rerun returned FAIL/status 1 (`ENOENT`). Time `/dev/null`
rerun returned FAIL/status 1 at VERSION (`ENOTTY`), before GET_TIME. Synthetic
runner cases returned status 1 with a failed summary for empty, malformed,
non-object, metadata-only, truncated, failed, missing-field, invalid-type/out-of-range,
duplicate-index, nonzero-flags, reversed-host, backward-GPU, mismatched-metadata,
and stalled-time data. A valid synthetic unit-rate case passed analysis.
[Reproducer](../results/2026-10-04-driver-time/integration-review/verify_runner.py)
and [results](../results/2026-10-04-driver-time/integration-review/verification.json)
are retained. Failure injections are software tests; no malformed hardware
response, permission denial, timeout, reset, or failed GPU submission was induced.

## Follow-up: P2, backend and shader-counter review

Reviewed `tests/gles_compute.c`, `scripts/run_compute.py`, and the completed
[P2 report](../experiments/baseline/compute-readback.md)/evidence. The C probe's
identity, allocation, barriers, bounded completion, whole-buffer copy/unmap and
cleanup gates were inspected; no material C defect required an edit. The runner
hardcoded `cc`; it now honors `CC` and `PROBE_INCLUDE`/`--mesa-include` and adds
`--smoke`. `make compute` performs two dispatches (constant 32 and index 33),
two initialization-only readback controls and three negative checks. The full
original matrix remains available separately.

Independent read-only rederivation matched **all 3,328 main/control output words**
across 26 retained primary cases (22 dispatches, four readback controls), including
all guards/padding. Original retained and primary manifests matched (418 and
365 files respectively), and wrong-oracle/invalid-shader/wrong-device checks
were verified. The selected P2 primary snapshots/hashes remain original evidence;
updated runner snapshots are retained with the smoke rerun.
[Verification script](../results/2026-10-04-compute-readback/integration-review/verify_stored.py)
and [results](../results/2026-10-04-compute-readback/integration-review/verification.json)
are versioned. The C probe remains byte-identical to the original snapshot.

One bounded `make compute` rerun passed both dispatches, every readback word,
pre/post controls and all three negative checks. Build bound was 30 s, each
API child bound 15 s, fence wait deadline 5 s. No full GPU matrix was rerun.
A missing `CC` override produced compile-launch failure and FAIL/status 1 with
no API child or dispatch. [Smoke evidence](../results/2026-10-04-compute-readback/integration-review/smoke/summary.json)
and compiler-failure logs are retained. No unexpected GPU fault/reset occurred.

Added `PROBE_INCLUDE` (default unchanged vendor Mesa include root) to the Make
and shared runner interface; `CC` remains independently configurable/exported.
Normal `make check` passed all six `tests/*.c` and all seven `scripts/*.py` present
at its snapshot, including in-progress `vulkan_caps.c`/`gles_time.c` syntax only.
The source hashes did not change during that check. Those owners can continue
editing afterward; this check does not certify their final code or execute their
probes. A changed source set/hash during a future check now produces FAIL.
[Check snapshot](../results/2026-10-04-compute-readback/integration-review/syntax-check.json)
identifies the checked source versions. `tests/vulkan_compute.c` appeared after
that snapshot and passed one separate syntax-only check with unchanged source
hash during compilation. It was not run, reviewed for execution correctness,
or staged. Neither ongoing file/runner/report/result set was edited or staged
in this review. Further concurrent additions/edits are outside these snapshots.

Reviewed and preserved [backend inventory](../results/2026-10-04-backend-inventory/README.md)
and [counter research](../results/2026-10-04-shader-counter-research/README.md).
Original capability/source hashes were verified before selecting compact JSON,
small probe sources and relevant source excerpts. Historical original manifests
are distinguished from new retained manifests. Findings now have versioned
support; bulk vendor source snapshots and executables remain in scratch.

P2 now demonstrates real Mesa-compiled GLES compute with exact readback on the
checked Asahi node/renderer. It does not identify emitted native instructions
or validate raw AGX bytes. Counter research found no justified timer selector.
Inspected source's compute timestamp offset mismatch and zero disjoint getter
predict timing hazards if they match the installed build; no loaded timing
result was produced by this review. The counter report's 24 MHz host-counter
claim was corrected to retain the T6022/G14D versus T6021/G14C provenance limit.
The backend report now links completed P2 without treating its earlier capability
inventory as execution evidence.

## Next tasks

1. Separately review ongoing Vulkan capability/runtime and GLES timer work when
   their owners finish; do not infer extension support from source or proc addresses.
2. Preserve P2 guards/control oracle while obtaining exact installed-driver native
   code provenance and, if available, an unchanged shader binary export/import path.
3. Validate command timestamp writes/completion/readback with the queried timebase;
   distinguish firmware command time, GL API time, host elapsed time and ISA cycles.
4. Seek primary provenance for an exact G14 timer instruction/selector before a
   bounded shader-counter experiment. No arbitrary SR scan is justified here.

The first commit was `79f2b3438595db556623ebc21f8bc4670e09b688`. Follow-up staging
is restricted to completed P2/backend/counter files and shared integration work;
ongoing Vulkan/timer work is excluded. Code/doc whitespace checks pass; original
raw logs may retain trailing blank lines to preserve evidence. Commit and remote
verification are reported in the handoff.

## Instruction-priority integration

Reviewed six offline mov/add/mul-low/mad-low candidates. Exact baseline/modified
bytes, XOR and changed bits agree with the report; all 36 uint32 fixtures were
independently recomputed. r31/r30 and configured relative roots passed. Added
`make instruction-candidates`; roots are configurable, module origins checked,
and output is clearly offline. Candidate JSON/source provenance is
[versioned](../results/2026-10-04-agx-instruction-candidates/README.md).
This is assembler/source-bitfield consistency, not emulator or G14 execution.

Integrated the completed [Vulkan capability corrections](../results/2026-10-04-vulkan-capabilities/review.md)
and [GLES calibration corrections](../results/2026-10-04-gles-timing/review.md),
including the scoped [invalid elapsed finding](../novel-results/2026-10-04-gles-elapsed/README.md).
Retained selected hashes, final Vulkan repeats/current-source snapshots, and
original/revised GLES buffer oracles were checked read-only. Ten original loaded
elapsed results and the revised one-dispatch confirmation remain incompatible
with their host brackets; timer calibration remains FAIL. No capability queries,
GPU timer runs, compute dispatches or instruction patches were executed in this
integration. One `make check` passed for its source snapshot; concurrent
execution files were syntax-checked only and were not edited or staged.

Next priority is an unchanged opaque shader binary roundtrip followed by one
controlled native arithmetic edit with guarded exact host readback. Agent6151's
Vulkan compute, binary patcher and execution report/result files remain separately
owned and in progress, outside this commit.

Concrete patcher review concerns for the coordinator:

- The loaded Vulkan ICD reports Mesa **25.3.6** while reference packing source
  is **26.3-devel** and applegpu describes G13. Retain exact ICD hash, shader
  binary UUID/version and exported bytes; source structure similarity alone
  cannot justify opaque payload offsets or integrity fields.
- Require a demonstrated unchanged export/import/readback control before edits.
  Parse and validate container/code bounds and integrity using the matched format;
  never globally replace a hex substring or infer code boundaries from a hit.
- These templates require low physical r32 registers and specific unsigned,
  uncached, unsaturated/unshifted modifiers. Prove one complete decoded baseline
  site and live initialized source; destination must feed checked output data,
  never addresses, bounds, loops, descriptors or masks. Preserve non-immediate
  fields, metadata, surrounding instructions and instruction length, then re-decode.
- Test one edit at a time with unchanged controls, full guards/padding/control
  buffers and independent modulo-2^32 expected output. Preserve imported/exported
  hashes and a minimal byte diff; stop on import, completion or oracle failure.
  Successful import or changed output alone does not establish intended semantics.

## Native move-immediate integration

Agent6151 finished packaging; final reports/manifests and a passing combined
record were reviewed after its process exited. The requested acm result tool
was unavailable in this session. No owned file was edited/staged while packaging
was active. The completed independent native-placement report is included as
source/model review, not a second modified-instruction hardware observation.

Independent stored checks matched **1,984 words across 15 readbacks**. Ten
baseline dispatches establish unchanged opaque export/import; four move-test
imports include unchanged before/after controls and patched counts 33/257.
Payload changes `0x12345678→0x12345679`; guards, inactive lanes and patterned
same-buffer tail remain intact. Wrapper SHA1 was recomputed independently; only
blob byte `0x954` (instruction bit 16) and digest bytes differ. Destination r2,
kill=0, code/metadata/preamble and the data-only store path are preserved.
Stale digest returned 1000482000 at shader creation with no queue submission.

One integration fix suppresses vendor bytecode writes in the offline patcher.
Offline regression reproduces identical patched/stale bytes and disassembly;
the stored verifier explicitly permits only this reviewed source change and
preserves original snapshots. `make check` and the new `make agx-instruction`
entry's command expansion passed. No extra GPU, capability or timer run occurred.
[Review evidence](../results/2026-10-04-vulkan-binary-roundtrip/integration-review/verification.json)
and [hardware scope](../experiments/arithmetic/first-agx-instruction.md) are linked.

P3/P4 now have a precise G14C B1 move-immediate field observation, not a novel
architecture discovery or validation of every decoded surrounding instruction.
Next: separately test the independently decoded index imadd addend 0→1, preserving
its cached/sign-extended operands and exact modulo-2^32/XOR oracle. That site is
an offline proposal in the independent report; subsequent concurrent ALU work is
outside this integration. Broader register/operand coverage remains pending.

## Multiply-add addend integration

The index shader's previously proposed immediate addend 0-to-1 edit now has
[hardware evidence](../experiments/arithmetic/imadd-addend.md). Kimi K3 through
acm-dev produced the pinned patcher/runner, offline rejection tests, and a passing
bounded run. Patched counts 33/257 match the modulo uint32 product-plus-one/XOR
oracle; unchanged imports before/after match baseline, with guards/padding/tail
intact. Independent coordinator recomputation matched 800 words across six
readbacks and exact instruction bit40/blob byte0x957. Stale SHA1 returned
1000482000 before any submission. No arbitrary instructions or SRs were scanned.

GLM 5.3 through acm-dev supplied a decoder-independent stored verifier; it passed
227 scratch checks before provider funding failure. Kimi likewise stopped on a
provider access error after execution. The coordinator packaged original evidence
as hex, adapted the verifier to committed artifacts, strengthened missing-case/log
checks and exception paths, and added module-origin validation to the patcher.
Original run source snapshots remain unchanged. No final agent review report is
claimed. New offline checks include software-only addend 63/64/255 fixtures, not
additional hardware observations. Shared Make/README entry points are integrated.

Known coverage gap: no fixed product `0xffffffff` tests addend carry into zero,
and only this one destination/operand combination was executed. Timing and shader
counter identification remain open; the failed GLES elapsed calibration remains
unresolved. Next: a separately pinned fixed-input carry test, then wider register
and immediate coverage, retaining unchanged controls and whole-buffer oracles.

## Special-register hardware follow-up

The user-authorized exhaustive SR scan completed all 256 selectors with three
single samples and three paired samples separated by 128 native adds. No ticking
selector was identified. Prefix/sparse masks establish scoped SR16 lane-position,
SR57 four-lane population, and SR59 32-lane population behavior. Copilot reviewed
evidence through ACM and wrote an independent verifier; the coordinator ran all
serialized hardware probes and integration checks. See the
[complete report](../experiments/registers/special-register-scan.md).
