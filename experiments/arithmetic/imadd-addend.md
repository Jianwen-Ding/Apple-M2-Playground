# G14C B1 integer multiply-add: immediate addend 0 to 1

**Observed hardware result:** in the pinned index shader, changing instruction
bit 40 changed the stored values exactly from
`((i * 0x9e3779b9) mod 2^32) XOR 0x12345678` to
`((i * 0x9e3779b9 + 1) mod 2^32) XOR 0x12345678`.
Patched counts 33 and 257 passed. Unchanged imports before and after returned
the original values. All guards, rounded inactive lanes and the patterned tail
remained intact. Six complete buffers contained 800 checked uint32 words.

This supports the existing model's immediate addend interpretation in one
eight-byte instruction on the driver-reported Apple M2 Max (G14C B1), Mesa
25.3.6. It is a hardware validation of a known field, not a newly discovered
opcode or a general characterization of AGX integer arithmetic.

## Reproduce

```sh
make agx-imadd      # bounded hardware suite; five dispatches and one no-dispatch readback
make verify-imadd  # offline patcher rejection tests and retained evidence verification
```

The runner requires the same pinned ICD and isolated runtime as the
[move-immediate baseline](first-agx-instruction.md). It compiles the unchanged
Vulkan delivery child, validates generated index SPIR-V, exports a control and
requires its exact hash before producing a patch. Modified cases import opaque
native bytes; they do not recompile SPIR-V. Compiler children have a 30-second
limit, other children 15 seconds, and the Vulkan fence a five-second deadline.
Any unexpected failure stops the suite. Paths can be configured through the
runner's `--runtime`, `--include`, `--grammar`, `--cc` and `--output` arguments.

## Hypothesis and one-field edit

The [prior independent placement review](native-control-disassembly.md) proposed
the site before execution. Control SHA256 is
`d0b99dace1de6eb2467c64ce872e8f5c02458d1edae0a3f74b9ed2c17cff0ba3`.
The native payload begins at blob `0x8bc`, main at native `0x80`, and the
target at native `0x96` / blob `0x952`:

```text
9e09820659000000  imadd r2.cache, r1.cache.sx, u8.sx, 0
9e09820659010000  imadd r2.cache, r1.cache.sx, u8.sx, 1
```

Only byte `0x957` changes outside the refreshed wrapper SHA1 at bytes 48–67.
Destination, multiplicands, cache hints, sign extension, shift, saturation and
negation remain identical. The patcher walks decoded instruction boundaries
from main, verifies exact decoded fields and preserves the preamble. Its pinned
post-target decode shows r2 used by XOR and then as store data; address registers,
bounds and execution-mask control remain unchanged.

These decoded names and dataflow are source/model interpretations. The exact
full-buffer response below is the independent hardware evidence. Sign extension
of 32-bit multiplicands does not change the low 32 product bits, so these outputs
cannot distinguish signed from unsigned multiplication.

| Case | Count | Result |
| --- | ---: | --- |
| No dispatch | 33 | Initial sentinel, guards and tail preserved |
| Exported index source | 33 | Original product/XOR oracle |
| Unchanged import before | 33 | Original product/XOR oracle |
| Patched import | 33 | Product plus 1, then XOR |
| Same patched bytes | 257 | Product plus 1, then XOR |
| Unchanged import after | 33 | Original product/XOR oracle |
| Patched instruction with stale wrapper SHA1 | 33 | Shader creation returned 1000482000; no submission or readback |
| Wrong node `/dev/null` | 33 | Rejected before logical-device creation |

Patched witnesses include `i=0: 305419897`, `i=1: 2349019074`,
`i=32: 3571147097`, and `i=256: 625864569`. The oracle checks every word;
these examples do not replace the complete comparisons. Cross-workgroup counts
also exercise masked excess lanes.

## Evidence, independent verification and limits

[Retained evidence](../../novel-results/2026-10-04-imadd-addend/README.md)
contains original logs, command bounds/statuses, source snapshots, exact shader
hex, decoded fields, wrapper hashes, and binary readbacks represented as hex.
The independent verifier uses a restricted Mesa field transcription, without
importing the execution patcher or applegpu decoder, and recomputes the complete
oracle. Its additional addend fixtures are offline tests, not hardware cases.

Only immediate C=0/1, destination r2 and the fixed multiplier/XOR were executed.
The inputs do not test an addend carry from `0xffffffff` to zero, saturation,
high multiplication results, general register allocation or other operand types.
The observation yields no shader timer selector, latency or throughput result;
the timing request remains open. The matched release source and wrapper behavior
are provenance for this pinned experiment, not proof of all distribution patches
or a portable serialization ABI. Kernel metadata was captured during integration
and is explicitly labeled; device/driver identity and hashes come from the run.

Next useful work is a separate fixed-input carry-boundary experiment, followed
by other immediate bits and operand/register classes with the same controls.
