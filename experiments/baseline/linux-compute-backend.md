# P2 Linux compute execution-path reconnaissance — 2026-10-04

The shortest available path to the first constant-write/readback control is
**surfaceless EGL + OpenGL ES compute through installed Mesa**. A capability-only
probe successfully created an ES context on the Asahi render node. No shader
was compiled or dispatched, and no GPU-written buffer was read back in this
inventory. P2 was subsequently established by the separate
[compute/readback experiment](compute-readback.md); it does not establish a
raw AGX byte replacement path.

For future controlled AGX instruction replacement, investigate **Vulkan
`VK_EXT_shader_object` binary export/import** after repairing its runtime
dependency. Local Mesa source serializes AGX code and metadata through this
interface; that is a software/source hypothesis, not a demonstrated installed
driver capability. GLES establishes the control sooner, but does not expose a
standard interface to supply raw AGX instruction bytes.

The completed report and [selected evidence](../../results/2026-10-04-backend-inventory/README.md)
are now versioned. The original regenerable binary and bulk scratch inventory
remain in `/scratch/apple-m2-playground/backend-inventory/`. No vendor changes, package
installation, dependency builds, kernel dispatch, commit, or push occurred.
Other agents' files were left untouched. `/scratch/Apple-M2-Playground` was not
used as canonical source.

## Observed environment and capability checks

Fresh checks ran at approximately 20:09–20:12 UTC. Commands had 10-second
inventory or 15-second compile/API limits; none timed out. API checks ran in
child processes. EGL context creation can initialize driver resources; these
checks did not create a shader, record a workload, or call a dispatch API.

| Check | Observed result | Evidence |
| --- | --- | --- |
| Installed packages | Mesa Vulkan/DRI/EGL 25.1.9; Vulkan loader 1.4.313.0; libdrm 2.4.133 | `inventory.json`, `rpm -q` command record |
| Vulkan manifest | Asahi ICD points to `/usr/lib64/libvulkan_asahi.so`; manifest advertises API 1.4.328 | `inventory.json`, file text/hash |
| Vulkan loader | `libvulkan.so.1` dynamically loads | `dependency-check.json` |
| Asahi Vulkan ICD | Dynamic load fails: `libdisplay-info.so.2` missing; `ldd` agrees | `dependency-check.json`, `inventory.json` |
| Vulkan instance | `vkCreateInstance=-9` (`VK_ERROR_INCOMPATIBLE_DRIVER`), probe exit 3 | `vulkan-capabilities.json` |
| Vulkan diagnostic | Loader finds Asahi manifest, cannot load ICD dependency, reports no drivers | `vulkan-loader-diagnostic.json` |
| EGL | `libEGL.so.1`, `libEGL_mesa.so.0`, and `libgallium-25.1.9.so` load | `dependency-check.json` |
| EGL context | Surfaceless display initializes as EGL 1.5; ES 3.1 request and surfaceless `eglMakeCurrent` succeed | `egl-capabilities-device.json` |
| EGL device association | `EGL_EXT_device_drm` and `EGL_EXT_device_drm_render_node`; device `/dev/dri/card1`, render node `/dev/dri/renderD128` | `egl-capabilities-device.json` |
| GL identification | Renderer `Apple M2 Max (G14C B1)`; `OpenGL ES 3.2 Mesa 25.1.9`; GLSL ES 3.20 | `egl-capabilities-device.json` |
| Compute limits | 1024 maximum workgroup invocations; 80 shader-storage buffer bindings | `egl-capabilities-device.json` |
| Compute functions | `glDispatchCompute`, `glBindBufferBase`, `glMemoryBarrier`, `glFenceSync`, `glClientWaitSync`, `glMapBufferRange` resolve through `eglGetProcAddress` | `egl-capabilities-device.json` |
| OpenCL/GLES front libraries | No `libOpenCL.so.1`, no OpenCL vendor manifests, no `libGLESv2.so.2`; related packages absent | `inventory.json`, `dependency-check.json` |
| Development tools | `cc` available; `clang`, `meson`, `ninja`, `vulkaninfo`, `clinfo`, `eglinfo`, `glslangValidator`, `glslc`, `spirv-as`, `spirv-dis`, `xcrun` absent on PATH | `inventory.json` |
| Development headers | System Vulkan/EGL/GLES/OpenCL headers absent; installed DRM headers present; Mesa checkout includes Vulkan, EGL and GLES headers | `inventory.json`; local source inspection |
| Scratch builds | No matching `build.ninja`, `meson-log.txt`, `meson-info.json`, Asahi/Vulkan `.so`, or AGX `.a` found by bounded `rg --files --hidden /scratch` inventory | `inventory.json`, command exit 1 (no matches) |

The renderer name and limits are **driver-reported observations**. They are
not independent measurements of GPU identity, core count, ISA semantics, or
successful compute execution. The Vulkan manifest's API version is likewise
metadata, not an enumerated device capability. Function addresses alone do not
prove execution; the successful context, limits and render-node association
make GLES the strongest current candidate.

The first EGL check used a `DRI_PRIME` hint. A follow-up omitted that hint and
queried the actual EGL device/render-node association; prefer that follow-up
evidence. No software renderer was reported. A future runner should fail if
the queried render node or expected renderer differs.

## Archived bounded checks

The versioned evidence directory contains `inventory.py`, `dependency-check.py`,
`vulkan-capabilities.c`, `run-capabilities.py`, and `egl-capabilities.py`.
Inventory records full commands, exit statuses, stdout/stderr, file hashes,
package versions and source revisions. Probe output wrappers preserve API
results and environment overrides. Original scratch hashes are retained as `original-manifest.json`; the selected
files have their own `retained-manifest.json`. `source-references.json` records
original source hashes, and `source-excerpts.json` preserves relevant lines.

These archived helpers preserve their original scratch output paths and source
assumptions; use the integrated P2 runner for routine verification. Archived
helper entry points are:

```sh
python3 results/2026-10-04-backend-inventory/inventory.py
timeout 10s python3 results/2026-10-04-backend-inventory/dependency-check.py
python3 results/2026-10-04-backend-inventory/run-capabilities.py
timeout 15s env LIBGL_ALWAYS_SOFTWARE=false python3 results/2026-10-04-backend-inventory/egl-capabilities.py
```

The recorded EGL child also removed inherited `MESA_*`, `ASAHI_*`, `AGX_*`,
`HK_*`, `EGL_*`, `LIBGL_*`, `GALLIUM_*`, `LD_PRELOAD` and `LD_LIBRARY_PATH`
overrides. Reproduce with the same clean environment. Vulkan checks forced
only `/usr/share/vulkan/icd.d/asahi_icd.aarch64.json` using both
`VK_DRIVER_FILES` and `VK_ICD_FILENAMES`, and disabled implicit layers using
`VK_LOADER_LAYERS_DISABLE=~implicit~`. The diagnostic added
`VK_LOADER_DEBUG=error,warn,driver`. No lavapipe fallback was accepted.

The small Vulkan probe compiled with `cc -std=c11 -Wall -Wextra -Werror -O2`,
`-I/save/workspace/AGX_Probe/mesa/include` and `-ldl`. It links no Vulkan SDK
development library: `dlopen`/`vkGetInstanceProcAddr` resolve the installed
loader. It contains physical-device/queue/memory queries, but the instance
failure prevented those calls. It never creates a logical device.

## Concrete implementation path for the first control

Implement a standalone runner in the canonical project's test/scripts area
under separately delegated ownership. It needs only Python `ctypes` and the
installed EGL runtime, or C using the checkout's unchanged EGL/GLES headers,
`dlopen`, and `eglGetProcAddress`. No Mesa build, SPIR-V compiler, Metal, or
OpenCL dependency is needed for GLSL ES source compilation.

1. Use `eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, ...)`,
   `eglInitialize`, `eglBindAPI(EGL_OPENGL_ES_API)`, `eglChooseConfig` with
   `EGL_OPENGL_ES3_BIT`, and `eglCreateContext` requesting ES 3.1.
   `eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, context)` passed
   here. Query `eglQueryDisplayAttribEXT(..., EGL_DEVICE_EXT, ...)` and
   `eglQueryDeviceStringEXT(..., EGL_DRM_RENDER_NODE_FILE_EXT)` and enforce
   `/dev/dri/renderD128`. Capture GL renderer/version and compute limits.
2. Create and link a `GL_COMPUTE_SHADER` with `#version 310 es`, local size
   `(32,1,1)`, one `layout(std430, binding=0)` uint SSBO, and a single
   `output[gl_GlobalInvocationID.x] = 0x12345678u` store. Retain shader source,
   compilation/link logs, checksums and all GL errors. Fail on errors.
3. Allocate 40 uint32 words with `glBufferData`, initialize every word to
   `0xcdcdcdcdu`, and bind using `glBindBufferBase(GL_SHADER_STORAGE_BUFFER,0,...)`.
   With one 32-thread workgroup, words 0–31 should change and words 32–39
   should remain sentinel guards. No CPU write of the expected output after
   initialization is allowed.
4. Use `glUseProgram`, then exactly one `glDispatchCompute(1,1,1)`.
   Follow with `glMemoryBarrier(GL_BUFFER_UPDATE_BARRIER_BIT |
   GL_SHADER_STORAGE_BARRIER_BIT)`, `glFenceSync`, and finite
   `glClientWaitSync(GL_SYNC_FLUSH_COMMANDS_BIT, ...)` waits capped at five
   seconds total. Reject `GL_WAIT_FAILED` or exhaustion; do not map on failure.
5. After completion, `glMapBufferRange(..., GL_MAP_READ_BIT)` the whole
   160-byte buffer, copy it to host-owned bytes, unmap, and compare all 40 words
   exactly against an independent host oracle. Save expected/actual bytes and
   checksums, including guards. Enclose the whole child in a process timeout
   since mapping or driver calls may themselves block.

The above was the inventory's proposed first control. The separate P2 probe
now implements an ES 3.2 variant with additional leading guards, padding, index
workloads and untouched-buffer controls; use its report and evidence as the
completed implementation. Keep that first dispatch isolated from raw
ISA replacement and retain every failure record.

## Mesa source execution paths (software evidence)

Read-only source root: `/save/workspace/AGX_Probe/mesa`, revision
`e5f0687867f5c5e88619175d9b0442f8560e8d53`, version `26.3.0-devel`.
Installed Mesa is `25.1.9`; these references explain the checkout, not the exact
installed binary. Line numbers below are specific to this revision.

| Path relative to Mesa root | Concrete reference and purpose |
| --- | --- |
| `src/gallium/drivers/asahi/agx_state.c:1964` | `agx_create_compute_state` accepts `PIPE_SHADER_IR_NIR`; it asserts TGSI kernels are unsupported. Direct Gallium is not an installed raw-byte API. |
| `src/gallium/drivers/asahi/agx_state.c:1478` | Backend invokes `agx_compile_shader_nir`; executable preamble/data BO setup follows. |
| `src/gallium/drivers/asahi/agx_state.c:5282`, `:5353` | `agx_launch` builds pipeline/USC state; `agx_launch_grid` handles the Gallium compute grid. |
| `src/gallium/drivers/asahi/agx_batch.c:644`, `:866` | Batch submission builds compute/render command and `drm_asahi_submit` structures and synchronization. |
| `src/gallium/drivers/asahi/agx_pipe.c:710`, `:912` | CPU transfer synchronization and `agx_transfer_map`. |
| `src/asahi/lib/agx_device.c:166`, `:231`, `:110` | GEM allocation, CPU mmap-offset/map, and VM binding. |
| `src/asahi/lib/agx_device.c:502`, `:740`, `:462` | Device/VM setup, scheduling queue creation, and actual Asahi submit ioctl. |
| `src/asahi/vulkan/hk_cmd_dispatch.c:124`, `:90`, `:56` | Vulkan dispatch entry point → compute state/grid → USC/CDM launch. |
| `src/asahi/vulkan/hk_cmd_buffer.c:678` | USC allocation and uniform/root-descriptor bindings. |
| `src/asahi/libagx/libagx_dgc.h:224` | `agx_cdm_launch` command packing, parameterized by chip, grid, workgroup and USC. |
| `src/asahi/vulkan/hk_shader.c:1195`, `:942`, `:1816` | NIR compilation → shader upload → `hk_fast_link`. Upload handles preamble/rodata separately from linked main code. |
| `src/asahi/lib/agx_linker.c:83`, `:123`, `:151` | `agx_fast_link` allocates executable low-VA BO, copies main code, and appends termination/setup. Preserve this machinery when changing instructions. |
| `src/asahi/vulkan/hk_queue.c:267`, `:887` | Submission through device operations and queue synchronization. |
| `src/asahi/vulkan/hk_physical_device.c:210`, `:1334` | Checkout advertises shader objects and host-visible/coherent memory. Not queried on installed Vulkan. |

The installed `/usr/include/drm/asahi_drm.h` supplies GEM/VM/queue/submit
structures, including compute command state. Presence does not prove all
kernel features work. A direct DRM runner must reproduce buffer VA bindings,
shader metadata, USC/CDM packing, scratch/shared-memory state, synchronization,
and cleanup; sending instruction bytes alone is insufficient. It is a larger
first step than the working GLES context path.

`AGX_MESA_DEBUG` options in `src/asahi/compiler/agx_compile.c:38` include shader
dumping, verbose disassembly and preamble control. No general raw-byte override
was found in the inspected Asahi/Gallium source search. Debug dumps are useful
software evidence; they do not establish hardware semantics or guarantee an
exact reproducible machine-code export from the installed package.

## Candidate raw-instruction replacement path

After Vulkan can enumerate the Asahi GPU, query `VK_EXT_shader_object` support,
its feature bit, and shader-binary UUID/version. Do not infer these from the
newer checkout. Establish the same constant-write control using Vulkan storage
buffers, dispatch, a compute-write→host-read barrier, finite fence wait,
`vkMapMemory`, and cache invalidation for any noncoherent mapping.

If supported, use `vkCreateShadersEXT` with SPIR-V, `vkCmdBindShadersEXT`, and
`vkGetShaderBinaryDataEXT`. First import the **unchanged exported binary** with
`VK_SHADER_CODE_TYPE_BINARY_EXT` and repeat exact readback. This tests the
binary round trip without changing ISA behavior or vendor source.

Source hypotheses for a later standalone blob patcher:

- `src/asahi/vulkan/hk_shader.c:1675` serializes `hk_shader_info`,
  `agx_shader_info`, code/data sizes, AGX code bytes and data bytes;
  `:1596` deserializes them and calls upload/linking. These structures include
  the ABI/register/preamble information that a replacement must preserve.
- `src/vulkan/runtime/vk_shader.c:380` and `:418` wrap that payload in a
  `MesaVkShaderBin` header and validate driver ID, UUID, version, length and
  BLAKE3 integrity. A payload edit without recomputing the exact matching
  format's integrity field should fail import; do not hard-code offsets from
  this checkout into an installed-25.1.9 patcher.
- Only after matching the installed driver format, decoding the control,
  identifying a same-size instruction span, and preserving metadata and
  termination should one controlled instruction field be changed. Exported
  shader binaries are opaque implementation data, not a portable AGX ABI.

This approach may avoid a custom submission backend, but is **unproven** here.
If the installed extension or binary format cannot be used, revisit a
standalone direct-DRM runner based on the verified local UAPI; do not patch
vendor Mesa to create an override. No instruction replacement was attempted.

## applegpu dependencies and remaining failures

Source root `/save/workspace/AGX_Probe/applegpu`, revision
`4c5bae61086b8067231120c98b4756d7696d399c`. Offline imports of `fma`, `srgb`,
`applegpu`, `disassemble` and `assemble` passed with bytecode writes disabled.
The assembler/decoder use Python and local modules; no build was needed.
`assemble.py:36` exposes `assemble_multiline`; `disassemble.py:8` exposes
`disassemble`. They provide candidate encodings and software-model checks,
not G14C hardware validation. Encoding experiments are another owner's work.

`hwtestbed/Makefile` requires `xcrun`, macOS Metal compilation, Metal framework
linking and Objective-C++; `hwtestbed.py:56` and `:94` can auto-run make and
archive compilation; `metallib_replacer.py:32` can also auto-build helpers.
Do not instantiate those harness classes on Linux. Their Metal archive
replacement mechanism does not provide Linux DRM submission.

Failure boundaries: Vulkan is blocked at ICD loading, not at shader execution
or a demonstrated kernel UAPI mismatch. EGL succeeded despite absent GLES
front-library files because entry points came from `eglGetProcAddress`.
OpenCL is not locally ready. Scratch search found no ready Mesa backend build;
the search is a bounded filename inventory, not proof no arbitrary binary
exists elsewhere. This inventory produced no GPU instruction, constant-write, readback or timing
result; the subsequent P2 hardware result is separately evidenced.

Next tasks after the completed [GLES P2 control](compute-readback.md): preserve
exact readback while obtaining native-code provenance; repair/query the Vulkan
runtime path through the coordinator's
environment work; query installed shader-object support and test unchanged
binary round trips; then design a format-matched external instruction patcher.
