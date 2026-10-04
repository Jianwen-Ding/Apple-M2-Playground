# Shader counter reconnaissance: G14C B1 — 2026-10-04

**Result: no justified shader-readable timing register, counter index, or timer
instruction bytes were found in the inspected primary evidence.** The special
register read encoding is source-supported, but its identified register map
contains no timer. This is an evidence gap, not a finding that hardware lacks
such a counter. Do not derive an AGX register index from ARM `CNTPCT_EL0`, scan
unnamed SRs, or treat firmware timestamp memory as a live shader clock.

The installed EGL/GLES stack does expose command timing APIs. A bounded
capability check succeeded without shader execution. Source inspection found
two material reliability concerns: an upstream compute timestamp offset mismatch
and a constant-zero disjoint getter. Validate command timestamp writes before
using this driver for compute microbenchmarks.

## Scope and evidence classes

Read `/save/workspace/AGENTS.md`, `/save/workspace/AGX_Probe/AGENTS.md`, repository
methodology and references, [driver time](driver-time.md), and
[P1](../baseline/device-params.md) first. The user's current instructions override
the older instruction to push and the older repository location. Canonical
source is `/save/workspace/apple-documentation-playground`. This assignment owns
only this report; concurrent changes to other files were left alone. No agents
were spawned, vendor files edited, commits made, or pushes attempted.

* **Existing driver observations:** P1 reports generation 14, variant C,
  revision `0x11`, chip `0x6021`, 38 enabled cores, and command timestamp
  frequency **1,000,000,000 Hz**. The G14C B1 / M2 Max name is a source
  interpretation of those fields, also returned by the GLES renderer below.
* **Existing host timer observations:** GET_TIME advances approximately at
  host elapsed-time rate. The pinned kernel implementation reads ARM
  `CNTPCT_EL0` and converts configured counter ticks to nanoseconds. The retained
  24 MHz configuration excerpt is T6022/G14D, not this T6021/G14C device;
  its frequency remains a source hypothesis compatible with timestamp residues. This supplies
  neither an AGX SR index nor shader read semantics.
* **New API observations:** context creation and capability/state queries
  described below. These are observations of installed software responses;
  no shader ISA behavior or loaded command duration was measured.
* **Source conclusions/hypotheses:** encoding fields, named SRs, timestamp
  plumbing, and predicted failure modes. They need hardware validation on
  this revision before becoming hardware findings.

Selected capability output, original manifests, and source excerpts are
[versioned](../../results/2026-10-04-shader-counter-research/README.md). Full source
snapshots remain under `/scratch/apple-m2-playground/shader-counter-research/`. `local-manifest.json`
records 22 source/header snapshots with original paths and SHA-256;
`remote-manifest.json` records URLs, retrieval times, hashes, and failures.
`source-search.json` retains the bounded source search; `environment.json`
records kernel, installed RPM/source RPM, vendor commits and worktree status.
These scratch artifacts are regenerable and are not the canonical repository.

## Primary compiler, decoder, and trace evidence

Local Mesa commit: `e5f0687867f5c5e88619175d9b0442f8560e8d53`.
Local applegpu commit: `4c5bae61086b8067231120c98b4756d7696d399c`.
The inspected source files were snapshotted rather than modified. Mesa's
worktree already contains unrelated symlink/deletion differences, recorded in
the environment artifact; a clean vendor tree is not claimed.

| Primary source at those commits | Supported conclusion | Limit |
| --- | --- | --- |
| Mesa `src/asahi/compiler/agx_opcodes.py:115–150,325–328` | Named SR enumeration and four-byte `get_sr` family with base opcode `0x72`; ordinary reads may be reordered | No SR named clock/timer; compiler scheduling properties do not establish hardware timing-read ordering |
| Mesa `src/asahi/compiler/agx_pack.c:501–503` | SR low six bits go to instruction bits 16–21; remaining SR bits start at bit 26 | Encoding a number does not establish what that SR reads |
| Mesa `src/asahi/isa/AGX2.xml:715–750,890–894` | Decoder calls the instruction `mfsr` (display `mov`); SR field is bits 16–21 and 26–27; named map has no timer | This XML is a software description, not a G14C B1 experiment |
| applegpu `applegpu.py:24–66,2216–2243,2372–2395` | `get_sr` selector has six low plus two high bits; parser accepts 0–255; execution model implements only SR80 | Parser range is not a list of safe or meaningful hardware reads; model cannot validate a timer |
| applegpu `hwtest.py:39,51,623`; `hwtestbed.py:171,185` | Existing shader examples read thread position, SR80 | Metal harness examples are not timing-register traces or Asahi executions |
| Mesa `src/asahi/compiler/agx_compile.c:1721–1734` and `libagx/helper.cl:24–38` | SR20 is core identity; SR144/146/147 carry helper operation and arguments | Helper words, including a low/high pair, supply no timer evidence |
| Mesa `src/asahi/vulkan/hk_physical_device.c:114,445–447` | KHR_shader_clock and both device/subgroup clock features are disabled | Software support absence does not prove hardware absence |
| Mesa `src/asahi/lib/decode.c:27–32`, `lib/wrap.c:24–34` | Command trace decoder routes shader bytes to the ISA disassembler; `oob_timestamp` reference concerns macOS IOKit interface tracing | The trace-related word timestamp is not a shader counter encoding |
| Mesa `src/asahi/libagx/query.cl:139–149` and `vulkan/hk_query_pool.c:383–412` | A shader can copy a firmware-written timestamp from memory; Vulkan splits compute control streams for timestamps | Copying a recorded value does not read a free-running shader clock |

The [primary applegpu G13 reference](https://dougallj.github.io/applegpu/docs.html)
also describes special-register reads, but does not identify a shader timer.
Its G13 scope must not silently become a G14C claim. A downloaded immutable
[applegpu source](https://github.com/dougallj/applegpu/blob/4c5bae61086b8067231120c98b4756d7696d399c/applegpu.py)
matches the local file hash
`986f6c6ec5547c5f61e357c7c0df614cb05b3382eed705d4ef7a79c4d3a2c46f`.

[Asahi's primary AGX notes](https://asahilinux.org/docs/hw/soc/agx/)
describe timestamp pointers and timestamp commands in firmware microsequences.
That is evidence for firmware instrumentation, not an AGX shader SR mapping.
The installed UAPI (`asahi_drm.h:842–877,1114–1146`) explicitly describes
start/end timestamp writes at command granularity. A compute command may contain
many dispatches, so a timestamp pair need not isolate one dispatch.

Searches covered the local compiler, ISA definition/decoder, applegpu model and
hardware harness, libagx query/helper kernels, driver query paths and trace
wrapper, plus the primary upstream references above. This was bounded
reconnaissance, not an exhaustive search of all Apple binaries or all upstream
history. Compiler cycle estimates (`agx_performance.c`) and spill instruction
distance accounting (`agx_spill.c`) are models, not counter-read implementations.

### Exact evidence gap and candidate admission rule

Missing is a primary shader disassembly or compiler implementation that connects
**a specified AGX instruction and selector** to **a progressing time value**,
with generation/revision provenance and read width. None of the inspected
sources supplies that connection. No candidate timer bytes/index are proposed.

A useful follow-up source artifact would contain the original shader or
documented intrinsic, compiler/OS version, complete unmodified binary and its
hash, decoded timer instruction and surrounding stores, device generation,
and evidence that the value changes with elapsed execution rather than lane,
dispatch or core identity. A G13 trace could justify a separately labelled
G14C compatibility hypothesis; it would not confirm G14C semantics. A vendor
profiler duration with no shader binary would not close this gap.

Once justified, instrumentation must preserve both reads and their ordering:
ordinary Mesa `get_sr` is reorderable, so inserting an arbitrary read into the
current IR does not establish a timing boundary. Inspect emitted bytes and
document ordering/side effects before execution. Width, atomicity of split
reads, timer frequency, clock domain, lane/core scope and read overhead remain
unknown. Reading a firmware timestamp buffer inside a shader could obtain a
previous command's value; the copy kernel provides no supported live-update or
intra-dispatch polling method. No MMIO mapping or host-updated shared counter
experiment is justified by this evidence.

## Installed EGL/GLES capability check

Archived capability reproducer (writes JSON to stdout; no shader execution):

```sh
timeout 20s python3 -B results/2026-10-04-shader-counter-research/egl_inventory.py
```

The recorded run exited 0 within the 20-second bound; stderr was empty.
`egl-inventory.json`, `.stderr` and `.status` retain output/status. The script
loads `libEGL.so.1` with Python ctypes, obtains procedures with
`eglGetProcAddress`, creates a Mesa surfaceless GLES context, queries metadata,
and destroys the context. It compiles, links and executes no shaders, submits
no draws/dispatches, and creates no asynchronous timer query objects. It makes
three synchronous GL timestamp state reads separated by two requested 10 ms
sleeps. Context setup may allocate driver resources; this is not an ioctl-only
probe.

| Observed response | Value |
| --- | --- |
| EGL version / vendor | 1.5 / Mesa Project |
| GL renderer | Apple M2 Max (G14C B1) |
| GL version / shading language | OpenGL ES 3.2 Mesa 25.1.9 / GLSL ES 3.20 |
| Timer extension | `GL_EXT_disjoint_timer_query` present |
| `GL_QUERY_COUNTER_BITS_EXT` | 64 for both elapsed and timestamp; GL error 0 |
| One disjoint state read | 0; GL error 0 |
| Synchronous `GL_TIMESTAMP_EXT` samples (ns per API) | 1,246,215,935,958; 1,246,226,002,125; 1,246,236,063,416; all GL errors 0 |
| Present procedures | EXT begin/end/query-counter, 64-bit result and availability getters, GLES compute dispatch and fence/client-wait |

Successive GL timestamp deltas were 10,066,167 and 10,061,291 ns. Three samples
establish progression for this API call only, not resolution, rate accuracy,
wrap width or command timing. GL exposes no shader-clock extension in this
recorded extension list. Procedure addresses alone do not establish extension
support; the extension list and counter-bit queries were checked separately.

Installed packages are `mesa-dri-drivers` and `mesa-libEGL`
`25.1.9-1.fc42.aarch64`, source RPM `mesa-25.1.9-1.fc42.src.rpm`.
GLES shared library and EGL/GLES development headers were not found in the
initial inventory. They are unnecessary for this ctypes check; a future C
runner can use proc-address loading plus checked declarations or obtain the
matching development packages through the coordinator. EGL fence facilities
provide synchronization; they do not supply shader timestamps.

### Timing path and reliability concerns

The local vendor commit is newer/different source than the installed package.
To avoid equating them, the relevant primary files were separately downloaded
from the upstream **mesa-25.1.9** tag and retained with hashes. This matches
the advertised version, not Fedora patches or an exact binary build. No
installed binary implementation equivalence is claimed.

1. **Compute timestamp destination mismatch (source-supported concern).**
   Upstream [25.1.9 `agx_pipe.c:1551–1555`](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/asahi/agx_pipe.c#L1551)
   sets both start and end offsets to `comp_start`. Its
   [batch cleanup:215–223](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/asahi/agx_batch.c#L215)
   consumes distinct `comp_start` and `comp_end` words. The local vendor commit
   has the same mismatch. If this path is in the installed binary, the end
   write can overwrite the start word while `comp_end` lacks a corresponding
   write. Elapsed subtraction or timestamp MAX reduction can then use invalid
   boundaries. This predicts unreliable results; no corrupt hardware result
   was induced here. Do not assume one particular bogus value or repair vendor
   sources under this assignment.
2. **Disjoint flag is not independent validation.** Both inspected versions'
   [GL getter](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/mesa/main/get.c#L1341)
   return constant zero. The observed zero therefore does not demonstrate
   detected clock changes, resets, contention, or absence of interruptions.
3. **Queries track batches, not individual instructions.**
   [25.1.9 `agx_query.c:337–345,576–592`](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/asahi/agx_query.c#L337)
   seeds a timestamp query with GET_TIME and MAX-reduces completed batch ends;
   elapsed queries MIN/MAX-reduce batch boundaries. Empty timestamp queries
   can be host reads. Two queries within one pending batch can share its end,
   so subtracting them may report zero or batch/host effects. An empty elapsed
   query is not a substitute for a minimal dispatch control.
4. **Host state timestamp is not completion timing.** The successful
   synchronous GL timestamp reads use the screen timestamp path in inspected
   source, ultimately GET_TIME. Their progression validates neither the
   firmware write path nor elapsed queries with compute work.

The [Khronos GLES extension specification](https://registry.khronos.org/OpenGL/extensions/EXT/EXT_disjoint_timer_query.txt)
defines nanosecond results, nonzero counter-bit support, asynchronous result
availability, and disjoint rejection. It distinguishes a synchronous state
timestamp from a completed-command query. It also permits different clocks for
elapsed and timestamp targets and warns about tile rendering granularity.
Check GL errors, read results through the 64-bit getter, poll availability with
a deadline, and bracket measurements with disjoint reads. A fence wait and host
clock give completion elapsed time including submission and scheduling costs.
They do not turn these query values into instruction cycles.

## Concrete next experiment (planned; not executed)

**First validate raw compute-command start/end timestamps using the now-completed
[P2 compute/readback control](../baseline/compute-readback.md).**
P2 uses GLES and does not expose direct UAPI command construction; a separate
verified submission/timestamp backend is still required for this raw path. This bypasses the suspicious Gallium
offset selection without modifying Mesa. The backend owner should extend their
owned runner, not this report's owner editing shared backend files.

1. Verify Asahi identity and query the command frequency again. Use one known
   good dispatch per compute command. Bind a timestamp BO with the UAPI
   timestamp usage; use the returned object handle and distinct, valid
   eight-byte destinations: start offset 0 and end offset 8. Initialize them
   to different sentinels and retain their pre/post raw bytes.
2. Use the established compute/readback shader and a controlled unsigned
   recurrence `x = x * 1664525u + 1013904223u` from a runtime buffer seed,
   storing the result. One group of 64 lanes, repeat counts 0, 64 and 256;
   count 0 still submits and stores data. Verify every output against host
   modulo-2^32 arithmetic. Inspect generated code to ensure the workload was
   retained; elapsed results describe that emitted workload.
3. Bound the whole run to 60 s and each completion wait to 2 s. Use eight
   warmup dispatches and at most 32 measured samples at each count (104
   dispatches maximum). Stop on the first failed completion, unchanged
   sentinel, inconsistent readback, or backward timestamp. No automatic reset
   or retries on faults. Record raw ticks, status, frequency, host brackets,
   controls and concurrent-work limitations; preserve failures.
4. Accept the timestamp plumbing only when both destinations are written,
   ordering is sensible and repeat runs agree within recorded variability.
   Convert ticks with the queried frequency. Report distributions and
   count-dependent slopes with controls; do not multiply by maximum GPU
   frequency to claim cycles. Small or equal deltas need larger *bounded*
   workloads, not invented timer resolution.

**Then calibrate GLES timing against that reference**, using the completed
GLES compute/readback control: one query interval per isolated dispatch,
64-bit elapsed result, explicit flush, availability deadline and checked SSBO
readback after a bounded fence wait. Compare the same three workloads. Retain
elapsed results and separate timestamp pairs; reject all-zero, wrap-sized,
nonresponsive or incompatible values. Check the Fedora source/build provenance
and command offsets before relying on the GLES compute result. If the mismatch
is present, use the verified raw UAPI path; driver changes belong to a separate
coordinator-assigned task. Graphics timing would need its own framebuffer and
tile/batch controls and would not establish compute instruction latency.

## Verification and failure modes

The context inventory completed and all recorded GL checks returned no error;
its bounded behavior and absence of shader/draw/dispatch calls were inspected.
Source/API JSON parsed, snapshot hashes were checked, and the report's local
links were verified. No whole-repository tests were needed for this report-only
change. No shader counter was assembled or executed and no unknown SR scanned.

The direct Khronos download returned HTTP 403, although web inspection worked;
the primary Khronos GitHub repository supplied the retained specification.
Upstream 25.1.9 requests for `src/asahi/isa/AGX2.xml` and the obsolete
`src/mesa/state_tracker/st_cb_queryobj.c` path returned 404. The former's local
newer XML is retained with its own provenance; query implementation was found
in the fetched `src/mesa/main/queryobj.c`. Missing development headers and the
absent standalone GLES library were worked around through EGL proc addresses.
These are source/tool failures, not GPU failures. No shader fault, GPU reset,
hang, unsupported timer-query error or loaded timing failure was observed.

Remaining tasks are the precise shader-timer provenance gap, raw timestamp
validation, exact installed driver build/patch inspection, and GLES
workload calibration. Hardware instruction timing remains unestablished.
