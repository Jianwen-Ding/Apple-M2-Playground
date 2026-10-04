# P2 compute/readback evidence — 2026-10-04

The final surfaceless EGL/OpenGL ES 3.2 suite passed on the checked Asahi
`/dev/dri/renderD128`, renderer `Apple M2 Max (G14C B1)`, Mesa 25.1.9.
22 real compute dispatches and four initialization-only controls matched every
payload, guard, padding and untouched-control word. This is submission/readback
evidence, not an AGX ISA or timing result.

Reproduce from the canonical repository:

```sh
python3 -B scripts/run_compute.py
```

Read [the full experiment](../../experiments/baseline/compute-readback.md) for
oracles, bounds, acceptance gates, failure modes and limits. The independent
sources are [gles_compute.c](../../tests/gles_compute.c) and
[run_compute.py](../../scripts/run_compute.py). Shared integration exposes `make compute` with a reviewed smoke subset.

## Retained files

- `primary/`: complete final run, excluding the regenerable executable.
  `summary.json` records the build, 25 ordered cases, final control, and negative
  checks. `environment.json`, `inventory/`, `compiler/`, library/source hashes,
  actual compiler dependency list/hashes, and exact probe/runner snapshots
  capture provenance. Its original scratch directory was
  `/scratch/apple-m2-playground/compute-runs/20261004T202323.409342Z-4168`.
- Each successful case: `command.json`, raw `stdout.txt`/`stderr.txt`, complete
  `shader.comp`, `compile.log`/`link.log` (empty logs mean no messages),
  `input.bin`/`output.bin`/`expected.bin`, separate control buffer input/output/
  expected files, and `verification.json`. All binary arrays are little-endian
  uint32, including guards. Output is copied from a fenced GPU buffer before
  unmapping; expected bytes are computed separately in Python.
- `primary/negative-oracle/`: one intentionally wrong expected word and the
  exact mismatch against `23-index-257/output.bin`. This is an expected rejection.
- `primary/negative-invalid-shader/`: rejected shader, compilation log,
  status 0 and exit 3. It creates no buffers, dispatch or readback.
- `primary/negative-device/`: wrong required device path rejected before shader
  creation. Its initialization can create driver resources, but no dispatch.
- `failure-missing-headers/`: end-to-end compiler failure and runner FAIL summary;
  `failure-missing-device/`: requested-node stat error, EGL node mismatch, runner
  FAIL summary and zero dispatches. Each includes its exact source snapshots.
- `host-failure-checks/`: synthetic sleeping child timed out and was killed as
  a process group, with partial stdout preserved; missing executable launch
  error also retained. These are host-only checks, with no GPU/driver calls.
- `previous-suite/`: summary, metadata, hashes and source snapshots of the
  preceding successful run `20261004T202238.369671Z-4036`. Its C probe is identical
  to the primary run; only runner path normalization was subsequently added.
  Full raw repeat output remains in scratch. The timeout/launch helpers tested
  in the host-only checks are identical in these runner snapshots.
- `review-verification.json`: read-only independent rederivation of all 3,328
  main/control output words, source-snapshot equality, negative-control results
  and manifest integrity. No GPU dispatch was added by this review.
- `integration-review/`: independent read-only verification script/results;
  reviewed two-dispatch smoke with full bytes/source snapshots and negative checks;
  shared all-probe syntax-check summary; `CC` launch failure without API children.
- `retained-manifest.json`: SHA-256 for every retained file except itself.
  Per-run `manifest.json` records each original scratch run except its executable
  and manifest. `binary_sha256` in the summary identifies the omitted executable.

The wrong oracle, invalid GLSL, device rejection, missing headers, missing device,
host timeout, and launch failure are deliberate negative checks. No unexpected
GPU error or timeout occurred. The driver fence-deadline and software-renderer
rejection branches were not induced. No machine-code mutation, raw DRM submit,
reset or vendor edit occurred. The original probe owner did not commit/push;
completed evidence is included in the subsequent integration commit.
