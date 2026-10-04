# Vulkan compute readback and unchanged binary roundtrip — 2026-10-04

**Passed on installed Honeykrisp, Apple M2 Max (G14C B1).** Hand-encoded,
validated SPIR-V compute shader objects produce exact guarded host readback;
opaque binary exports import unchanged into fresh child processes and produce
that same result. This establishes the raw AGX delivery harness. The subsequent
[one-field AGX instruction experiment](../arithmetic/first-agx-instruction.md)
also passed; capability enumeration was not the experiment's endpoint.

The selected combined suite has ten baseline dispatches, four instruction
experiment dispatches, one no-dispatch submission, and two rejection controls.
No timing or instruction throughput claim is made. Other agents were active;
concurrent workload and clock state were not measured.

## Reproduce

From the canonical repository:

```sh
python3 -B scripts/run_vulkan_compute.py
python3 -B scripts/run_vulkan_compute.py --probe-mov
python3 -B results/2026-10-04-vulkan-binary-roundtrip/verify_stored.py
```

The first command runs the baseline alone; the second runs the modest combined
suite with the instruction experiment and before/after controls. The third
verifies saved evidence without GPU access. `--output` must name a new directory;
default artifacts go to `/scratch/apple-m2-playground/vulkan-compute-runs/`.
`--cc` (default `$CC` or `cc`), `--include`, `--grammar`, and `--runtime` allow
explicit build/environment paths. This standalone runner does not import
shared `scripts/run.py`, build vendor sources, install packages, or change a
global environment. It reads Mesa headers/grammar and the existing isolated
runtime from the [earlier runtime repair](vulkan-runtime.md).

## Exact input and oracle

There is no installed `glslangValidator`, `spirv-as`, or `spirv-val` executable.
The runner encodes SPIR-V 1.3 reproducibly using the read-only Mesa checkout's
`spirv.core.grammar.json`. Generator word is zero, ID bound is 34, schema word
is zero. Each encoding JSON retains every instruction's opcode and operand
words, the used opcode schemas, enum values and grammar hash. `.comp` files
are the exact equivalent GLSL specification, **not compiler-generated inputs**.
Module bytes are reconstructible from the saved encoding JSON.

Both modules have workgroup size `(32,1,1)`, storage buffer set 0/binding 0,
and a four-byte push constant `count`:

```glsl
uint i = gl_GlobalInvocationID.x;
if (i < count) data[8u+i] = 0x12345678u;
// index variant instead stores (i * 0x9e3779b9u) ^ 0x12345678u
```

Bounded validation children dynamically call the installed SPIRV-Tools public
C ABI (`spvParseTargetEnv("vulkan1.3")`, `spvValidateBinary`). Both return 0.
SPIRV-Tools reports `v2025.2 unknown hash, 2025-05-07T00:00:00+00:00`.
No Vulkan validation layer is used; successful readback is not API validation.

| Artifact | SHA256 |
| --- | --- |
| Constant SPIR-V | `bb05b286ce434c908796ce55a335d7826e9083de8fbe09200d7a2e51dc8d32a5` |
| Index SPIR-V | `61b7c605200ff0935d8230cfb370036aa1f4675bddb064f48d2c72e35a33f66a` |
| Constant opaque export, 2572 bytes | `b79bd25941bdea1a0095b219fe0333ac5c18822225de811c9308a38702e9e098` |
| Index opaque export, 2572 bytes | `d0b99dace1de6eb2467c64ce872e8f5c02458d1edae0a3f74b9ed2c17cff0ba3` |

C initializes eight leading guards, a workgroup-rounded payload, eight trailing
guards, and a further 16-word untouched tail. Main words start at `0xcdcdcdcd`;
the tail starts at `0xa5a50000+j`. The tail is a separately patterned region of
**the same buffer**, not an independently allocated SSBO. Excess dispatched
lanes must leave padding intact. CPU never writes expected payload results.
Python independently computes the full expected uint32 vector, including
modulo-2^32 index multiplication, and accepts only exact whole-buffer equality.

Each source shader dispatches count 33 before export. The exported bytes are
hashed before and after every import, and imports at counts 1, 32, 33 and 257
run in distinct processes/devices without a SPIR-V fallback. Each import uses
identical descriptor/push-constant layout declarations. All ten baseline
readbacks pass. The initialization-only control remains entirely unchanged;
feeding that output to the dispatch oracle is rejected.

## Submission and runtime invariants

The C harness requests Vulkan 1.3, satisfying the shader-object extension's
version dependency. It checks/enables `shaderObject` and `dynamicRendering`,
and uses only ordinary 32-bit integer SPIR-V features. It selects a compute
queue, checks the small workgroup/dispatch bounds, binds the compute shader
object, compatible descriptor set and push constants before dispatch. Compute
needs no graphics pipeline or graphics dynamic state. These choices follow the
[Khronos extension dependencies](https://docs.vulkan.org/refpages/latest/refpages/source/VK_EXT_shader_object.html)
and [dispatch requirements](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdDispatch.html).

Memory selection requires HOST_VISIBLE|HOST_COHERENT. Observed type 0 has flags
`0xf`. Host-write → compute-read/write and compute-write → host-read barriers
surround dispatch; host reads only after successful fence completion. Coherence
removes the need for flush/invalidate. Every fence has a 3-second wait, every
GPU child a 15-second process timeout, compilation a 30-second timeout, and
inputs/exports a 1 MiB bound. Any fence/child failure aborts the suite; the
runner does not continue to further GPU submissions after such a failure.

Every readback child checks one physical device, exact renderer and Mesa 25.3.6
identity, Honeykrisp ID, requested render-node device numbers 226:128,
shader UUID `2313bd7c3909b8ad0f31883eab5c412e`, and binary version 0. UUID/version
are driver metadata, not decoded instruction-format identifiers. Runtime
hashes are checked before and after every readback case. The full dependency
closure, include/build dependency hashes and source snapshots are recorded.

- ICD: `26abaa59964177c0acf1860ba19cfd4b97c25435a8c4d81f9052973bc6bf1c65`.
- Loader: `779a58a2dd93644b81e7975d80e0a30e3a7beafc472f0937fde93a8840a90407`.
- Extracted libdisplay-info: `e65991680fa5770c58867a2d5b53108c4ae2f24ec37680b388afd35bf10b305e`.

Only child processes receive the scratch `LD_LIBRARY_PATH` and forced Asahi
ICD. Inherited driver/library overrides are removed, implicit layers disabled,
and shader caching disabled. Device rejection is enforced by checked identity,
not by environment hints. Existing driver package/source discrepancies remain
as described in the earlier runtime report; no additional capability inventory
or package provenance investigation was undertaken here.

## Failures and evidence

The `/dev/null` identity control exits 1 before `vkCreateDevice`, with no
submission/readback. The instruction experiment's stale SHA1 control returns
`VK_INCOMPATIBLE_SHADER_BINARY_EXT` (1000482000) before queue submission.
An initial checker incorrectly expected negative -1000482000: hardware cases
had passed, but the overall suite failed this control assertion. The newer
header defines the legacy error alias with the positive value. That run and
its source snapshots are retained as `failure-result-sign/`; the checker was
corrected and the final suite passes. A first offline patch attempt also
rejected the blob because the wrapper magic literal had an extra NUL; corrected
before any patched GPU submission. Neither was a GPU fault.

No GPU timeout, reset, guard corruption, binary fallback, or payload mismatch
was observed. Failure teardown relies on process exit; an actual timed-out GPU
would require separate recovery investigation, which was not exercised.

Selected final evidence: [results README](../../results/2026-10-04-vulkan-binary-roundtrip/README.md).
The final independent stored-data verification confirms 15 successful readback
vectors, 14 dispatches, reconstructed SPIR-V hashes, wrapper hashes, the single
instruction bit change, and unchanged source snapshots. No shared file or
vendor source edits, subagents, commits, or pushes were made by this task.

Integration exposes `make agx-instruction` for the same bounded combined suite.
The stored-source verifier now reports the sole reviewed patcher change:
reference bytecode writes disabled. Offline regression emitted identical blobs
and disassembly, so no further GPU run was required. All original captured sources
and hardware records remain historical evidence.
