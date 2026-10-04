# Vulkan binary roundtrip evidence — 2026-10-04

Final combined suite **PASS**. Ten baseline compute dispatches, four one-field
AGX instruction dispatches and one no-dispatch control matched their complete
host oracles. Wrong render node and stale binary integrity were rejected before
submission. This is hardware execution/readback evidence; identity/limits are
still driver-reported metadata.

- [Final record](primary/record.json): commands, statuses, all complete vectors,
  identity, code/binary/runtime hashes and embedded exact instruction blobs.
- `primary/*-oracle.json`: individual complete expected/actual vectors and API
  evidence; command directories retain raw stdout/stderr and return codes.
- `primary/{constant,index}-encoding.json`: exact SPIR-V words/schema;
  `.comp` files specify equivalent GLSL. Validation logs retain SPIRV-Tools
  success and version. `primary/sources/` snapshots the three owned executables'
  sources, including the external patcher; no built executable is stored here.
- [Instruction evidence](../../novel-results/2026-10-04-first-agx-instruction/README.md):
  full input/patched/stale hex, main/preamble disassembly and source layout.
- `failure-result-sign/`: failed overall suite because the Python checker
  expected a negative incompatible-binary code. Hardware readback cases passed;
  stale integrity returned positive 1000482000 and was rejected. This directory
  retains the original runner source and raw rejection, not a hidden GPU failure.
- [Independent stored verifier](verify_stored.py): recomputes every whole-buffer
  oracle and readback hash, reconstructs SPIR-V, checks wrapper integrity and
  instruction XOR, validates rejection and source snapshots without GPU access.

```sh
python3 -B results/2026-10-04-vulkan-binary-roundtrip/verify_stored.py
```

Final verification: `passed=true`, 15 successful readbacks, 14 dispatch readbacks,
instruction bit 16 only, stale integrity rejected before submit, source snapshots
match. Full binaries remain under
`/scratch/apple-m2-playground/vulkan-compute-runs/20261004T215043174006Z/`;
control blobs can also be recreated from the durable hex in the instruction
record. Earlier scratch runs retain the initial baseline and checker iterations.

See [baseline report](../../experiments/baseline/vulkan-binary-roundtrip.md) for
reproduction, synchronization, bounds and failure analysis. See
[instruction report](../../experiments/arithmetic/first-agx-instruction.md)
for the hardware finding and its narrow scope. These files remain uncommitted
for coordinator review; no shared files or vendor sources were edited by this task.

Integration review independently checked all 1,984 output words, raw API events,
patch bytes/digests and disassembly without GPU reruns.
[`integration-review/`](integration-review/verification.json) retains checks,
byte-identical offline patch regression, syntax snapshot, and the independent
native-placement review JSON. Current patcher differs from the captured source
only by suppressing reference bytecode writes; the verifier explicitly checks
that change and its regression hash. Captured sources remain unchanged.
