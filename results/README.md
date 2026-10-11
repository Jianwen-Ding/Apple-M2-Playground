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

- [2026-10-04 offline AGX instruction candidates](2026-10-04-agx-instruction-candidates/README.md):
  exact bytes, changed bits, mathematical fixtures and source provenance; no execution.
- [2026-10-04 Vulkan capabilities](2026-10-04-vulkan-capabilities/README.md):
  isolated runtime repair, physical-device and shader-object reports; no binary import.
- [2026-10-04 GLES calibration](2026-10-04-gles-timing/README.md):
  checked compute readback with invalid loaded elapsed results; pairs uncalibrated.

- [2026-10-04 Vulkan binary roundtrip](2026-10-04-vulkan-binary-roundtrip/README.md):
  exact unchanged imports, guarded readbacks and one native move-immediate variation.
- [First G14C move-immediate observation](../novel-results/2026-10-04-first-agx-instruction/README.md):
  one existing field supported by hardware; no novel architecture or broad ISA claim.
- [2026-10-10 SR geometry/core-id/bit-15](2026-10-10-sr-shape-core/README.md):
  per-lane values for nine shapes, 2048-workgroup SR20 sets, and 256-selector bit-15 sweeps.
- [2026-10-10 SR resources/widths](2026-10-10-sr-resources/README.md):
  shared-memory and metadata-edit sweeps for SR18/SR19; 64/16-bit get_sr destinations.
- [2026-10-11 grid-size cap](2026-10-11-grid-size-cap/README.md):
  control dispatch exact at 2^16..2^24 threads (X, Y, Z); sampled-row coverage exact to 2^30;
  cost tracks workgroup count (~2.7 ns/workgroup).
- [2026-10-11 ALU bit flips](2026-10-11-alu-bitflip/README.md):
  213 applegpu gap bits on 53 instructions; fmadd 10-byte lane-offset form; fmadd32 bit 52.
- [2026-10-11 sub-op spaces](2026-10-11-subop-spaces/README.md):
  every value of funop / iunop / simd_op / shuffle op fields.
