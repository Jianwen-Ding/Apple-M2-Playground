# Task 1 progress — 2026-10-04 integration review

Canonical source is `/save/workspace/apple-documentation-playground`; scratch
contains regenerable runs only. Reviewed the completed params/time C probes,
runners, reports, raw evidence, and provenance. Vendor Mesa/applegpu sources
were not modified. The separately owned backend report was not edited or staged.

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
- P2–P4 remain pending; P5 has a driver baseline only. No shader execution,
  instruction behavior, ISA latency, or new physical counter semantics claimed.

Primary reports and retained evidence:
[parameters](../experiments/baseline/device-params.md),
[time](../experiments/timing/driver-time.md),
[params review](../results/2026-10-04-device-params/integration-review/verification.json),
[time rerun](../results/2026-10-04-driver-time/integration-review/hardware/summary.json).
Original source/header hashes remain historical; reruns record reviewed code.

## Changes and verification

Added `make params` / `make time` and matching shared runner commands. `make check`
now parses all current script Python files and syntax-checks all current C probes
using C11 and warnings as errors. It passed for smoke/params/time after the
initial code changes; the final numeric range guard was exercised by synthetic
checks and the final time rerun. A concurrent owner then added `gles_compute.c`:
default `make check` correctly failed on missing system EGL headers. All four
current probes passed with
`make check CC='cc -I/save/workspace/AGX_Probe/mesa/include'`, reading unchanged
vendor headers. This is syntax verification only; the GLES file remains outside
this integration commit. Selected check summaries are retained alongside the
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

## Next tasks

1. Review the separately owned Linux compute backend investigation when complete.
2. Establish P2 with bounded allocation/submission/completion and exact constant
   buffer readback; preserve Asahi identity and header hashes in each run.
3. Validate command timestamp writes/readback using the reported 1 GHz command
   timestamp frequency. This remains distinct from GET_TIME and instruction cycles.
4. Identify a justified G14 shader counter candidate with primary provenance,
   then validate bounded reads and memory results before timing instruction chains.
   G13 encodings and source timer mechanisms remain hypotheses until exercised.

Only finished params/time and integration files are eligible for the explicitly
authorized integration commit/push. No backend or unrelated concurrent work is
included. Staged whitespace checking passed for code/docs; four raw compiler
stdout logs retain their original trailing blank line to preserve evidence hashes. Commit identity and remote verification are reported in the final handoff.
