# Matched ordinary immediate-add evidence

Twenty-six gzip records preserve exact code/control bytes, complete input and
final buffers, guards, every repeat index, firmware timestamp, wait and
completion marker, source/binary hashes, kernel diagnostics and recovery
controls. There are 1,544 timed candidate submissions and 52 controls, with
zero fault events. All final buffers are exact; intermediate buffers are not
captured by the existing harness.

`make verify-integer-immediate-cost` uses no GPU. It rebuilds every unique
program and compares full functional simulation with independent arithmetic
oracles, including successive table states. It verifies source/harness/binary
provenance, complete readbacks, repeat ordering and all nonoverlapping probe
windows. It confirms equal instruction lengths, the exact immediate-field
difference, and byte identity of immediate-3 shaders to the earlier builder.

`analysis.json` binds every record, model binary, source and calibration input.
It retains chronological probe ordering, every timing sample, pooled and
per-trial immediate ratios and descriptive incremental slopes. Predictions
use explicit launch/uniform settings and a 1398 MHz modelling assumption.
Actual operating frequency is unmeasured. The one-chain timings have large
repeat-to-repeat variation, so pooled ratios are not calibration estimates.

The train runner now accepts explicit evidence destinations, name prefixes
and final-buffer oracles. Existing train defaults are preserved and its
earlier source is archived in the preceding evidence directory. Its CPU
parser/lock tests and the preceding 19-train offline verifier still pass.

[Interpretation and limits](../../novel-results/2026-10-20-integer-immediate-cost/README.md).
