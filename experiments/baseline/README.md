# Baseline probes

1. **DRM access:** existing `tests/drm_smoke.c`; opening the render node and
   querying driver identity has passed.
2. **Device identity:** query Asahi parameters, enabled cores, and available
   timestamp properties. Planned.
3. **Memory lifecycle:** allocate, CPU-map, initialize, and release a buffer
   using the verified local UAPI. Planned.
4. **Submission/readback:** submit a constant-write compute kernel, wait for
   completion, and compare an exact output buffer. Planned.

The submission/readback case is the control for later ISA experiments. Keep
source shader and emitted machine code, compiler details, and command setup.
