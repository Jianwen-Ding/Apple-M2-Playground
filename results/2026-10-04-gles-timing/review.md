# Independent review — 2026-10-04

Calibration **FAIL: invalid loaded elapsed timing**. Compute execution/readback
passed. Timestamp pairs are still uncalibrated. A successful characterization of
an invalid timer does not turn this calibration into a pass.

[review_evidence.py](review_evidence.py) independently checks all original
24 cases with an affine-map exponentiation oracle, rather than importing the
runner or repeating its recurrence loop. It compares inputs, outputs, guards,
control and seeds, including the retained expected files. Decimal host brackets
and integer query subtraction independently reproduce all ten invalid loaded
elapsed results. Original selected/raw hashes and Vulkan repeat provenance passed;
[the audit output](independent-audit.json) records that pre-edit check. Missing
files listed for original scratch manifests are omitted evidence artifacts, not
hash mismatches. The selected manifest covers the retained files.

Khronos' [extension specification](https://registry.khronos.org/OpenGL/extensions/EXT/EXT_disjoint_timer_query.txt)
defines elapsed results in nanoseconds and availability/disjoint checks. The
probe's fresh query objects, matched begin/end, post-availability 64-bit reads,
SSBO barriers, fence waits and guarded mapping are consistent with these APIs.
The synchronous timestamp state is diagnostic and does not validate completion
boundaries. No observed failure identifies the driver or firmware cause.

Corrections: honor tokenized `CC` (include-root override already existed), use
ES 3 core `glGetInteger64v` because the EXT getter is not required on ES 3,
remove duplicate tentative declarations and the oversized host input array,
classify `FAIL_INVALID_TIMER` separately from `FAIL_UNCALIBRATED`, report invalid
case names, and prevent a failed final control from leaving execution marked
verified. Calibration remains failed even when API/process failure is null.

Strict C builds and Python AST checks pass. [review-run](review-run/review.json)
retains a minimal revised-source hardware confirmation: initial control, empty
elapsed, one 256-repeat loaded elapsed dispatch, final control. All bytes passed
the independent oracle; the loaded result remains invalid and runtime library
hashes match the original. This adds one dispatch, not another full timing sweep.
[review-negative-node](review-negative-node/summary.json) tests `CC='cc -pipe'`,
rejects the wrong node before shader creation/dispatch, stops scaling and records
the failed final control. Existing CPU timeout and negative-oracle evidence remains
valid. No GPU hang or recovery was induced. Fresh contexts, concurrent work and
unmeasured clocks preclude workload slopes or physical-cycle claims.

The original captured sources and raw runs are unchanged. Current source behavior
and revised evidence are separate from the original capture. The small scoped
[finding](../../novel-results/2026-10-04-gles-elapsed/README.md) is ready for review.
Next: validate an independent command-timestamp reference and actual binary build
provenance before diagnosing cause or accepting timestamp pairs.
