# Selected Linux backend inventory — 2026-10-04

[Report](../../experiments/baseline/linux-compute-backend.md) describes the
20:09–20:15 UTC reconnaissance. This inventory created an EGL context and
queried capabilities; it did not compile or dispatch a shader. Later P2 execution
is documented separately in [compute/readback](../2026-10-04-compute-readback/README.md).

- `inventory.json`: original bounded commands, runtime/package/header/tool
  inventory, manifest contents and failures.
- `dependency-check.json`, `vulkan-capabilities.json`,
  `vulkan-loader-diagnostic.json`: historical missing `libdisplay-info.so.2`,
  ICD load/instance failure. These are distinct from ongoing Vulkan work.
- `egl-capabilities-device.json`: EGL calls, checked device/node, renderer,
  ES context and compute limits/functions. `egl-capabilities.json` is the earlier
  check; prefer the device-associated record.
- `source-references.json` and `source-excerpts.json`: original Mesa source hashes,
  revision, selected lines for compilation/submission/linking and shader binary
  serialization. They describe the checkout, not the installed Mesa binary.
- Original small probe scripts and `vulkan-capabilities.c` are archived for
  provenance. They retain their original scratch paths; the canonical shared
  execution control is `make compute`. No archived capability probe was rerun
  during integration.
- `original-manifest.json`: original inventory hashes, including the omitted
  regenerable executable and pre-integration report hash.
  `retained-manifest.json` hashes the selected versioned files instead.
  `integration-verification.json` records hash validation before selection.

No vendor source was edited. Bulk vendor snapshots and executables were omitted;
relevant source lines and complete original source hashes are retained.
