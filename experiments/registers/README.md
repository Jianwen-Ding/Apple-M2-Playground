# Register probes

Questions: 16/32/64-bit views and aliasing; uniform versus per-thread values;
source modifiers; discard hints; documented special-register reads.

First case: initialize distinctive bit patterns, change one register view,
store every affected view, and compare with a host bit-level oracle.
Requires known-good submission and readback. Treat G13 decoder assumptions as
generation-specific until checked on this device. Timing-related candidates
belong with `../timing/`.

[Completed special-register scan](special-register-scan.md): all 256 selectors,
paired reads, prefix/sparse execution masks, and repeated same-device dispatches.
The tested path yielded no clock; SR16/57/59 have reproducible lane/mask behavior.
[Copilot review and independent verifier](sr-copilot-review.md).

[Geometry, core id, and bit-15 form](sr-geometry-core-alt.md): nine 1-D to 3-D
shapes confirm workgroup/local/global SRs; SR7 = SIMD groups per threadgroup;
SR20 = (cluster<<4)|core matching driver core masks; bit-15 `get_sr` writes nothing observable.

[Resource registers and widths](sr-resources-width.md): SR18 = threadgroup memory
bytes, SR19 = register allocation; `get_sr` is 32-bit only (16-bit form = low half).

[Direct-DRM differential scan](sr-direct-drm.md) (2026-10-11): SR17 = hardware SIMD-group
slot, SR32 = pipeline-word offset, SR113 random, preshader word must be last.
