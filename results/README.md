# Retained evidence

Commit compact, relevant environment snapshots and raw outputs here. Keep bulk
logs and build products in `/scratch/apple-m2-playground/runs/`. Each retained
run needs a README explaining the command, what passed, and the limits of the
result. Do not publish temporary scratch paths as the only reproducer.

No novel ISA finding is implied by a successful environment or DRM access test.

- [2026-10-04 DRM baseline](2026-10-04-drm-baseline/README.md): successful
  driver-access check, environment snapshot, and exact command/output logs.

- [2026-10-04 device parameters](2026-10-04-device-params/README.md): raw driver
  identity/topology fields and source interpretation.
- [2026-10-04 driver time](2026-10-04-driver-time/README.md): bounded GET_TIME
  samples, structural validation, rate brackets and failures.
- [2026-10-04 compute/readback](2026-10-04-compute-readback/README.md): actual
  GLES dispatches, whole-buffer host oracles, controls and independent review.
- [2026-10-04 backend inventory](2026-10-04-backend-inventory/README.md): historical
  runtime/capability responses and selected source excerpts; no dispatch.
- [2026-10-04 shader-counter research](2026-10-04-shader-counter-research/README.md):
  source maps, timestamp concerns and synchronous GL state reads; no shader counter.
