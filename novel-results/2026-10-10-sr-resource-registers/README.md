# SR18 threadgroup-memory size and SR19 register allocation

On the driver-reported Apple M2 Max G14C B1 / Mesa 25.3.6, compute stage:

- **SR18** = threadgroup-memory allocation in bytes, rounded up to 256 (0 when none).
  It follows SPIR-V shared arrays of 128 B–32 KB and direct edits of the exported
  `local_size` from 256 to 65280, including in a shader with no shared-memory instructions.
- **SR19** = `max(8, roundup(nr_gprs, 8))`, the per-thread allocation in 16-bit
  registers. It follows 16 `nr_gprs` values from 1 to 255 and ignores `nr_preamble_gprs`.
- `get_sr` has no 64-bit form: no selector writes the high register. The 16-bit form
  returns the low half and preserves the destination's other half.

No other SR responded to shared memory, uniform count, texture/sampler counts, scratch
or register count. That rules those out as explanations for the SR15/24/25/97/114 constants.

Proof: `make verify-sr-resources` (offline, with failure injection). Hardware:
`make sr-shared`, `make sr-meta`, `make sr-width`.
[Report](../../experiments/registers/sr-resources-width.md) ·
[evidence](../../results/2026-10-10-sr-resources/README.md).
Observations from one device, not claims of first community discovery.
