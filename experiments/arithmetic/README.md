# Arithmetic and conversion probes

Questions: integer widths and carry, floating-point rounding, fused operations,
conversion modes, signed zero, infinities, NaNs, and subnormal inputs.

First case: a known arithmetic instruction with fixed input bits and a host
oracle. Compare bits, record acceptable differences explicitly, and vary only
one input or modifier at a time. Avoid using the AGX emulator as the only
expected-result source when checking a claim inherited from that emulator.

Requires working register setup, compute submission, and output readback.

Completed scoped hardware cases:

- [Move-immediate bit 0](first-agx-instruction.md).
- [Integer multiply-add immediate addend 0 to 1](imadd-addend.md).

Both use exact pinned native binaries and full guarded host readback. They
validate specific fields in existing instructions, rather than general ISA coverage.
