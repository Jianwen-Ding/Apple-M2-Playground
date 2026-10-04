# Isolated Asahi Vulkan runtime and capabilities — 2026-10-04

An isolated Fedora 42 `libdisplay-info` runtime repairs Asahi ICD loading.
Four bounded capability probes enumerate exactly one Honeykrisp device on
`/dev/dri/renderD128`. The driver reports Vulkan 1.4.328 and
`VK_EXT_shader_object` extension **and feature** support, including a binary
UUID and version. Three controls without the scratch runtime reproduce the
original missing-library failure. No logical device, shader, buffer, command
buffer, dispatch, binary export/import, or instruction mutation was created.

These are **driver-reported capabilities of an enumerated physical GPU**, not
independent hardware measurements or evidence of AGX instruction semantics.
Shader-object binary round-trip remains a future experiment.

## Runtime repair and provenance

The prerequisite [backend inventory](linux-compute-backend.md) found
`libdisplay-info.so.2` missing. The
[Fedora 42 package metadata](https://packages.fedoraproject.org/pkgs/libdisplay-info/libdisplay-info/fedora-42.html)
identifies `libdisplay-info-0.2.0-3.fc42` and the matching SONAME. The aarch64
runtime RPM was obtained from the
[official Fedora archive](https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/42/Everything/aarch64/os/Packages/l/libdisplay-info-0.2.0-3.fc42.aarch64.rpm).

- Signed RPM SHA256: `86fa707a83121deb20435b225615b76ff96a39b9b6fe9163f07218596e589ce3`.
- `rpmkeys --checksig --verbose`: RSA/SHA256 header signature key ID
  `105ef944` **OK**, header SHA256/SHA1 and payload SHA256/MD5 **OK**.
  Verification used the already installed Fedora 42 public key; no key import
  or global RPM database change was needed. The local key file is hashed in
  the evidence.
- An initial official Koji download had valid digests but **no signature**;
  it was not extracted or used. It remains in scratch, with SHA256
  `3e77106b92b1ceb055f8e55497353dec9fef7dae4f8acb4e4a364934919b03b0`.
  Its URL is `https://kojipkgs.fedoraproject.org/packages/libdisplay-info/0.2.0/3.fc42/aarch64/libdisplay-info-0.2.0-3.fc42.aarch64.rpm`.
- `rpm2cpio` decoded the signed payload. The runner's small Python `newc`
  extractor preserves the package's actual relative symlinks and hashes all
  member bytes. It rejects traversal, absolute/escaping symlinks, unexpected
  member types, and payloads over 10 MiB. Host `cpio` was unavailable.
  `libdisplay-info.so.2 -> libdisplay-info.so.0.2.0` is the **RPM-provided
  matching SONAME link**, not an ABI-spoofing link to a different version.
- Extracted files are under `/scratch/apple-m2-playground/vulkan-runtime/usr/`.
  Only child processes receive
  `LD_LIBRARY_PATH=/scratch/apple-m2-playground/vulkan-runtime/usr/lib64`.
  No global packages, linker configuration, ICD manifests, drivers, or
  vendor source files were changed.

The package runtime requirements are the aarch64 dynamic loader, libc and
libm: GLIBC 2.17, libm GLIBC 2.27, `GLIBC_ABI_DT_RELR`, and GNU hash support.
RPM also lists payload/parser requirements (`CompressedFileNames`,
`FileDigests`, `PayloadFilesHavePrefix`, `PayloadIsZstd`). The extracted
library's `ldd` resolves `/lib/ld-linux-aarch64.so.1`, `/lib64/libc.so.6`, and
`/lib64/libm.so.6`; it has no additional unresolved dependency.

The complete ICD dependency report is retained in each record. Existing
libdrm, zlib, zstd, XCB/X11 bridge and XAu libraries, xshmfence, Wayland client,
udev, SPIRV-Tools, expat, libstdc++, libgcc, libc/libm/loader, libffi and libcap
resolve from system locations. Only `libdisplay-info.so.2` resolves from
scratch. Removing the child override again leaves that dependency unresolved.

## Driver identity discrepancy

`rpm -q` and `rpm -qf` register `mesa-vulkan-drivers-25.1.9-1.fc42.aarch64`,
but **the actual Vulkan library is not the registered package's file**:
`rpm -V mesa-vulkan-drivers` exits 1 and reports `S.5....T.` (size, digest,
mtime differences) for both the Asahi library and its manifest. Its ELF
packaging note identifies `mesa`, `25.3.6-0.3.fc42`, aarch64, consistent with
runtime `driverInfo="Mesa 25.3.6"`. This task observed the discrepancy; it did
not establish how or from where the files were replaced.

- ICD SHA256: `26abaa59964177c0acf1860ba19cfd4b97c25435a8c4d81f9052973bc6bf1c65`.
- ELF build ID: `4145f84ae7bdcc482d00efc7cb7e84ea2663e631`.
- Loader RPM: `vulkan-loader-1.4.313.0-1.fc42.aarch64`; loader reports 1.4.313.
- Unchanged header/source checkout:
  `/save/workspace/AGX_Probe/mesa`, revision
  `e5f0687867f5c5e88619175d9b0442f8560e8d53` (`26.3.0-devel` in prior inventory).

Treat the prior report's installed-version statements as RPM metadata, not
proof of the Vulkan binary's version. Neither the newer checkout nor the
registered 25.1.9 package establishes this library's opaque shader format.

## Capability observations

The final two records have identical capability JSON and identical source,
header, loader, ICD, key and extracted-library hashes.

| Query | Observed result |
| --- | --- |
| Physical devices | Exactly 1; `Apple M2 Max (G14C B1)` |
| Driver | `Honeykrisp`, driver ID 26 (`VK_DRIVER_ID_MESA_HONEYKRISP`), Mesa 25.3.6 |
| Device API | Vulkan 1.4.328; probe requests instance API 1.1.0 |
| Device type / identifiers | Integrated GPU (1); vendor ID 65541 (`0x10005`), device ID 0; identifiers are software-reported |
| DRM association | `VK_EXT_physical_device_drm`; render major 226, minor 128, matches `/dev/dri/renderD128` |
| Compute queue | Family 0, one queue; flags `0xf` (graphics, compute, transfer, sparse binding); timestamp valid bits 64 |
| Compute workgroup limits | 1024 invocations; size `[1024,1024,64]`; count `[2147483647,65535,65535]`; shared memory 32768 bytes |
| Memory heap 0 | 33,619,443,712 bytes; `DEVICE_LOCAL` flag |
| Memory type 0 | Heap 0; flags `0xf`: device local, host visible, host coherent, host cached |
| Memory type 1 | Heap 0; flags `0x7`: device local, host visible, host coherent |
| Shader object | Extension spec version 1; `shaderObject=VK_TRUE` |
| Shader binary UUID | `2313bd7c3909b8ad0f31883eab5c412e` |
| Shader binary version | `0` (reported value, not an unsupported indication) |
| Additional core features | `shaderInt64=true`, `shaderInt16=true`, **`shaderFloat64=false`** |

The heap size is a driver-reported heap capacity; it does not measure physical
RAM or verify the owner's 64 GB specification. Memory flags do not prove
buffer allocation, coherence under dispatch, or readback. UUID/version do not
reveal payload offsets, portable AGX ABI, or a working binary importer.
Unsupported float64 is preserved rather than silently omitted. All enumerated
device extensions and their spec versions are retained in raw JSON.

## Reproduce

From the canonical repository:

```sh
python3 scripts/run_vulkan_caps.py --setup
python3 scripts/run_vulkan_caps.py
python3 scripts/run_vulkan_caps.py --without-runtime
```

The last command intentionally exits **1**, retaining `vkCreateInstance=-9`
(`VK_ERROR_INCOMPATIBLE_DRIVER`) and loader diagnostics for the missing
`libdisplay-info.so.2`. Successful commands exit 0. `--output /scratch/.../new`
selects a new evidence directory; existing directories are rejected to avoid
overwriting prior evidence. The setup is reproducible from the pinned archive
URL and SHA256; it verifies the signature before extraction. If the archive or
trusted local key is unavailable, setup fails rather than accepting unsigned
content. A missing compiler, unresolved dependency, malformed JSON, unexpected
ICD path, timeout, or physical-device identity mismatch also fails the runner.

The runner builds [the standalone probe](../../tests/vulkan_caps.c) with
`cc -std=c11 -Wall -Wextra -Werror -O2`, the unchanged local Mesa include
root, and `-ldl`. Vulkan calls resolve via `dlopen("libvulkan.so.1")` and
`vkGetInstanceProcAddr`; there is no Vulkan SDK link/build dependency.
A 30-second compile limit, 15-second per-command/probe limits, bounded
physical-device/extension/queue arrays (16/512/32), a 30-second download socket
limit and 1 MiB download size cap limit this reconnaissance. No probe timed out.
These are process bounds, not GPU fence tests.

Child environments remove inherited `VK_*`, `MESA_*`, `ASAHI_*`, `AGX_*`,
`HK_*`, `LIBGL_*`, `GALLIUM_*`, `DRI_*` and `LD_*` overrides. Both
`VK_DRIVER_FILES` and `VK_ICD_FILENAMES` force only
`/usr/share/vulkan/icd.d/asahi_icd.aarch64.json`; implicit layers are disabled
with `VK_LOADER_LAYERS_DISABLE=~implicit~`. Loader diagnostics show only that
manifest. Acceptance requires one integrated Honeykrisp physical device, a
compute queue, and the expected DRM render node. No lavapipe fallback is
accepted. Capability queries can initialize driver resources but this program
never creates a logical device or submits a workload.

## Evidence, verification, and next work

Selected logs and records are in
[results/2026-10-04-vulkan-capabilities](../../results/2026-10-04-vulkan-capabilities/README.md).
Python AST parsing and every strict C build passed. Four runtime-enabled probes
passed; three unmodified-environment controls failed as expected. Final repeat
comparison passed. RPM provenance, all dependencies, commands, exit codes,
stdout/stderr, environment overrides and hashes are preserved. No GPU hang,
unsupported shader-object result, binary import rejection, or submission fault
was observed or induced. Negative controls test ICD loading only.

Next separately owned tasks:

1. Establish a bounded Vulkan constant-write/readback control with an exact
   host oracle, guarded buffer and finite completion wait, enabling the queried
   shader-object feature when creating a logical device.
2. Export a SPIR-V-created compute shader with `vkGetShaderBinaryDataEXT`,
   import the **unchanged** opaque binary, and repeat the same readback.
   UUID/version and all relevant driver hashes must accompany the artifact.
3. Resolve exact source/package provenance for this loaded 25.3.6 driver
   before analyzing serialization or designing a format-matched external
   patcher. The local 26.3 checkout remains only a source hypothesis.

Do not infer any of these steps from extension enumeration. No vendor-source
modification, binary mutation, kernel dispatch, shared-file edit, commit,
push, or new agent spawning occurred in this task.

Independent review and correction verification: [compact record](../../results/2026-10-04-vulkan-capabilities/review.md).
