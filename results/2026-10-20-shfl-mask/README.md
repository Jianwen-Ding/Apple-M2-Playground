# Sparse-mask shuffle records

`run-113.json.gz` and `run-509.json.gz` are complete independent direct-DRM
hardware sweeps with different random payload/index seeds. Each retains 118
programs, exact code, all 21,520 table words and 3,104 main-output words per
program, controls, simulator gates, firmware events, source hashes, hardware
identity, AC state, boot identity and memory snapshots. Inputs reconstruct
from the seed; their SHA-256 hashes must agree before any oracle is checked.

The three output planes are low payload word, high payload word and arithmetic
predicate. Four preceding planes are read-only low/high payloads, indices and
active bits. A 16-word suffix is untouched. The separate main output has guards
and a patterned tail. Negative controls intentionally mismatch PTX data while
preserving all guards and predicates; all raw words still match the AGX model.

Reproduce with `scripts/run_drm_shfl_mask.py hardware --seed 113 --output NEW_DIR`
and again with `--seed 509`. Each program is gated in the simulator first.
`make verify-shfl-mask` verifies retained observations without accessing the GPU.
See the [finding](../../novel-results/2026-10-20-shfl-mask/README.md).
