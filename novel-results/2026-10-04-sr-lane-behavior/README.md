# Observed four-lane and active-population SR behavior

On the driver-reported Apple M2 Max G14C B1 / Mesa 25.3.6:

- SR16 reports physical position within four-lane blocks in this layout.
- SR57 reports active population within a four-lane block.
- SR59 reports active population within a 32-lane block.

Fifteen contiguous-prefix counts and a sparse even-index mask support these
descriptions. Sparse masks distinguish SR16 from the existing SR56 active-index
label: lanes 0 and 2 produce SR16=0/2, SR56=0/1. SR58 similarly packs active SIMD
positions. Scope is X-indexed compute workgroups of 32; these are new project
observations, not claims of first community discovery or universal register names.

Proof: `make verify-sr` independently compares every value with mathematical
oracles and verifies full guarded raw buffers. [Complete evidence](../../results/2026-10-04-sr-scan/README.md)
and [report](../../experiments/registers/special-register-scan.md) preserve exact
native bytes, SHA1/SHA256, predicates, controls and limits. Hardware reproduction
is available with `make sr-characterize` and `make sr-even`.

The associated exhaustive selector scan found no progressing clock through the
tested 32-bit `get_sr` path. That negative result does not establish absence of
shader timing hardware.
