# P2: bounded GLES compute and deterministic readback

Completed 2026-10-04 on the exposed Asahi device. **Real GPU compute submission
and exact host readback passed** through surfaceless EGL and OpenGL ES 3.2.
The final suite contains 22 dispatches, four initialization-only controls,
two repeats of each constant/index case at five sizes, and three negative
checks. All payload, guard, padding, and untouched-control words matched.
This establishes the P2 submission/readback control, not a new AGX ISA finding.

## Question and prior hypothesis

Can the context discovered in [backend reconnaissance](linux-compute-backend.md)
execute a simple, bounded compute shader and return independently predictable
bytes? The earlier context/entry-point checks did not establish execution.
The hypothesis was that installed Mesa could compile GLSL ES and submit it
on the EGL-associated Asahi render node without a GLES development library,
Vulkan dependency repairs, or vendor modifications.

## Reproduce independently

From `/save/workspace/apple-documentation-playground`:

```sh
python3 -B scripts/run_compute.py  # Full original matrix
make compute                     # Reviewed smoke subset: two dispatches
```

The runner imports only Python standard-library modules, never shared runner
internals. It builds the new `tests/gles_compute.c` in a unique scratch directory
with `CC` (default `cc`), `-std=c11 -Wall -Wextra -Werror -O2 -MD`,
Mesa checkout headers, and
`-ldl`. It dynamically loads installed `libEGL.so.1` and obtains EGL/GL entry
points through `eglGetProcAddress`. No Mesa/applegpu source is changed or built.
`PROBE_INCLUDE` or `--mesa-include`, `--scratch-root`, and `--device` override their paths; both
filesystem roots are resolved before use. The default artifact root is
`/scratch/apple-m2-playground/compute-runs/`. No package installation is needed
in the observed environment.

Manual single-case API probe, including its outer timeout:

```sh
cc -std=c11 -Wall -Wextra -Werror -O2 \
  -I/save/workspace/AGX_Probe/mesa/include tests/gles_compute.c \
  -ldl -o /scratch/gles_compute
mkdir -p /scratch/manual-compute-case
cd /scratch/manual-compute-case
timeout 15s /scratch/gles_compute index 33 /dev/dri/renderD128
```

A direct C run only records API status and readback: **only the Python runner's
independent whole-buffer oracle produces the experiment PASS**. Counts outside
1–257, unknown modes, or incorrect argument counts are rejected. Do not invoke
this probe without an outer timeout.

## Device and runtime observations

Every child obtains a surfaceless Mesa EGL display, initializes EGL, queries
its `EGL_DEVICE_EXT`, and requires that device's reported DRM render node to
match the requested path. It opens that exact node and requires
`DRM_IOCTL_VERSION` driver name `asahi`. It then creates and makes current a
surfaceless ES 3.2 context, requires renderer **exactly**
`Apple M2 Max (G14C B1)`, and verifies the context version and compute limits.
A software or different hardware renderer cannot pass the identity check.
`LIBGL_ALWAYS_SOFTWARE=false` is a hint; the checked device and renderer are
the acceptance conditions. Driver overrides and `LD_PRELOAD`/`LD_LIBRARY_PATH`
are removed; shader caching is explicitly disabled. Removed key names and
selected overrides are recorded without dumping arbitrary environment values.

| Driver/API response | Final suite observation |
| --- | --- |
| EGL version / vendor | 1.5 / Mesa Project |
| EGL associated nodes | `/dev/dri/card1`, `/dev/dri/renderD128` |
| Render-node device number | Recorded in `environment.json` |
| DRM name / description / version | `asahi` / Apple AGX Graphics / 0.0.0 |
| Renderer / GL vendor | Apple M2 Max (G14C B1) / Mesa |
| GL / GLSL ES | OpenGL ES 3.2 Mesa 25.1.9 / GLSL ES 3.20 |
| Maximum invocations / X size / X group count | 1024 / 1024 / 65535 |
| Installed packages and kernel | Raw RPM/compiler output and `uname` retained |

These identity strings and limits are driver-reported observations. The separate
[P1 parameter experiment](device-params.md) records generation 14, variant C,
revision `0x11`, chip ID `0x6021`, and enabled-core masks. Its product-name
mapping is source interpretation; this P2 probe does not repeat GET_PARAMS,
measure core count, or verify the owner-supplied 64 GB capacity. Runtime library
SHA-256 hashes, compiler dependencies and their hashes, and exact probe/runner
source snapshots are preserved. The newer Mesa checkout supplies API headers;
it is not claimed to be the source revision of installed Mesa 25.1.9.

## Shader, initialization, and host oracle

Each successful case compiles and links `#version 320 es`, high-precision
integers, and a workgroup of `(32,1,1)`. The payload shader is:

```glsl
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
void main() {
    uint i = gl_GlobalInvocationID.x;
    if (i < count) data[8u+i] = 0x12345678u;
}
```

The index variant replaces only the stored expression with
`(i * 0x9e3779b9u) ^ 0x12345678u`. Python computes multiplication modulo
2^32 independently for every logical index. The complete shader source is
retained per case, including the version, precision and workgroup declarations.

The main SSBO has eight leading guards, a rounded-up dispatched payload extent,
and eight trailing guards. Every word starts at `0xcdcdcdcd`. Logical payload
begins at word 8. The shader uniform is the actual count, so excess lanes in the
last workgroup must leave padding unchanged. A separate 16-word SSBO at binding
1 is initialized to `0xa5a50000 + j`; the shader never references it. Every run
maps and verifies that buffer too. No expected payload values are written by
the CPU into the GPU buffers after initialization.

| Logical count | Workgroups | Main buffer words | Guard/padding words after logical payload |
| --- | --- | --- | --- |
| 1 | 1 | 48 | 39 |
| 32 | 1 | 48 | 8 |
| 33 | 2 | 80 | 39 |
| 65 | 3 | 112 | 39 |
| 257 | 9 | 304 | 39 |

Each row uses eight leading guards. Counts 1, 33, 65 and 257 dispatch excess
lanes; 33/65/257 also cross workgroup boundaries. Both expressions run twice
at every size. Before that matrix, an initialization-only count-32 control,
two constant count-32 dispatches, and another initialization-only control run.
After the matrix, count-257 and final count-32 initialization-only controls run.
Those controls compile the same constant shader, initialize/bind its buffers,
and fence/read them **without calling `glDispatchCompute`**; every main word
must remain sentinel. Each case uses its own context and buffers in a new child.
This verifies clean baseline initialization/readback rather than persistence
of a single buffer across all trials.

The maximum main allocation is 1,216 bytes; the other buffer is 64 bytes.
The largest grid has 288 invocations, with only 257 permitted payload stores.
Python verifies the full input, expected output, actual output, and separate
control buffer, including exact byte length and every word. Binary artifacts
are explicitly interpreted as little-endian uint32; the runner rejects other
host byte orders.

## Completion and bounds

After each optional dispatch, the probe issues
`glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT | GL_BUFFER_UPDATE_BARRIER_BIT)`,
creates `GL_SYNC_GPU_COMMANDS_COMPLETE`, and uses `glClientWaitSync` with
`GL_SYNC_FLUSH_COMMANDS_BIT`. Each wait requests at most 50 ms. A monotonic
five-second deadline and maximum 100 calls bound the wait loop. A final call
can overlap the deadline by at most its 50 ms request plus driver-call overhead;
any blocking API call is also subject to the outer process timeout. Only
`GL_ALREADY_SIGNALED` or `GL_CONDITION_SATISFIED` permits mapping. Wait failure,
GL errors, or deadline exhaustion fails before readback. There is no `glFinish`.

`glMapBufferRange(GL_MAP_READ_BIT)` maps the full allocation only after completion.
Bytes are copied to host-owned storage, unmapping must report valid data, and
then artifacts are written. Build timeout is 30 seconds; package/compiler
inventory commands have ten-second bounds; every API child has a 15-second
outer timeout. Timeout kills the child's process group and allows at most two
more seconds for collecting output, preserving partial logs. A stuck kernel
call can survive SIGKILL; the runner does not wait indefinitely or reset it.
On unexpected API, timeout or oracle failure the suite stops further dispatches.

All successful final-suite compile/link statuses were 1, GL errors were zero,
and all 26 readback cases completed on the first fence wait with either
`0x911a` (`GL_ALREADY_SIGNALED`) or `0x911c` (`GL_CONDITION_SATISFIED`). Logged fence/host durations are completion
bound evidence, not GPU instruction latency. Other agents may run workloads
concurrently; clock state, thermal state and isolation were not measured.

## Negative checks and failures

| Check | Observed result | Scope |
| --- | --- | --- |
| Deliberately wrong oracle | Expected word 8 changed from `0x12345678` to `0x12345679`; checker identified exactly word 8, with actual/expected retained | Host comparison against already captured real GPU output; GPU bytes unchanged |
| Invalid GLSL identifier | Compile status 0, exit 3, log reports undeclared `INTENTIONAL_UNDECLARED_IDENTIFIER`; no link, allocation, dispatch or readback | Meaningful shader compilation rejection |
| Wrong required EGL device | Exit 1 at `render-node-identity`, before shader creation; actual associated node recorded | Device mismatch fails closed |
| Missing Mesa include directory | Compiler exit 1 for missing `EGL/egl.h`; runner exit 1; zero API children | Build failure preserved |
| Missing requested render node | `stat` error recorded; first initialization-only child rejected actual EGL node; runner exit 1; zero dispatches | End-to-end failure summary preserved |
| Deliberate host child sleep | 150 ms timeout, process-group SIGKILL, return -9, preceding stdout retained | Runner timeout path only, no GPU/driver calls |
| Missing child executable | Launch error retained, return code null, no timeout | Runner launch failure path only |

A final initialization-only control passed after the expected shader/device
rejections. Actual GPU fence timeout, GL mapping failure, software-renderer
rejection, and hung-driver recovery were not induced. Their fail-closed code
paths were reviewed; the host sleep does not simulate a GPU fault. No unexpected
GPU failure was observed. No invalid machine code, reset, raw DRM submission,
Mesa edit, or applegpu edit was attempted.

## Evidence and next tasks

[Selected evidence](../../results/2026-10-04-compute-readback/README.md) retains
all final-suite case shaders, input/output/oracle bytes, status/error logs,
commands and exit codes, identity metadata, compiler/runtime/source hashes,
and failed runs. A preceding successful suite's summary and source snapshots
are retained as repeat evidence; earlier full runs and all binaries remain
regenerable scratch artifacts. Versioned sources and this report are canonical.

A read-only review rederived all 3,328 main/control output words across the
26 final-suite readback cases, verified retained SHA-256 manifests, and checked
that the original C/Python sources matched the primary run snapshots.
Integration subsequently added `CC`/include configuration and a smoke subset to
the runner; the C probe remains identical. Original snapshots and hashes remain
historical evidence, while the reviewed smoke retains the updated runner. Its result
is retained as `review-verification.json`. The fence statuses were 22 condition-
satisfied compute cases and four already-signaled initialization-only controls.

This is a hardware execution/readback observation through Mesa's public API.
The GLSL expression does not identify which native instructions were emitted.
No AGX instruction bytes, native disassembly, encoding semantics, shader-readable
counter, or timing result was obtained. The standard GLES path does not expose
raw AGX replacement; source-level compiler/submission explanations remain
hypotheses about software, not measurements of ISA behavior.

Shared entry points now expose `make compute` with the two-dispatch smoke subset,
while the full original matrix remains reproducible. Independent integration
review rederived all 3,328 stored output words and checked manifests; the smoke
passed controls, constant/index readback and all three negative checks. See
[`integration-review/`](../../results/2026-10-04-compute-readback/integration-review/verification.json).
A missing `CC` override was rejected before any API child.

Next tasks: preserve this exact control while adding one controlled
shader operation per experiment; obtain matching installed-driver native-code
provenance if available; separately repair/query the Vulkan shader-object path
and test unchanged binary export/import before any instruction replacement.
No commit or push was performed by this task owner.
