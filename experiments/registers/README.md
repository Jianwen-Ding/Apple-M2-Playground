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
