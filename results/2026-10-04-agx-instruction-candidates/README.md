# Offline AGX integer candidates — 2026-10-04

**No hardware execution.** Six same-size immediate edits for mov/add/mul-low/
mad-low are templates, not shader container offsets or validated G14 encodings.
[Report](../../experiments/arithmetic/agx-instruction-candidates.md) and
[exporter](../../scripts/agx_instruction_candidates.py) describe their exact scope.

- `candidates.json`: baseline/modified little-endian bytes, decoder fields,
  XOR/changed bits, six uint32 mathematical input fixtures per candidate,
  placement constraints and reference hashes.
- `source-provenance.json`: reference commits/file hashes and brief Mesa packing
  excerpts. Agreement is applegpu assembler versus restricted Mesa-source
  transcription, not two compiled encoders or software-emulator results.
- `verification.json`: independent byte/bit/host-fixture and configured-root checks.
  `integration-check.json`: syntax-check snapshot only, including concurrent
  execution files without running or staging them.
- `manifest.json`: selected-file hashes.

Reproduce offline with `make instruction-candidates`; output goes to scratch.
Override `APPLEGPU_ROOT`, `MESA_ROOT`, and `SCRATCH_ROOT`, or use the script's
`--applegpu-root`, `--mesa-root`, `--dst-r32`, and `--src-r32` flags. Reference
modules are imported without bytecode writes; no GPU node, Vulkan/EGL runtime,
shader patch, or submission is used.

The execution owner must first validate an unchanged binary roundtrip. Each edit
needs a decoded instruction boundary and a proven initialized source/live output-
data destination, preserving all surrounding instructions and resource/control
state. Only guarded readback on G14C can establish hardware behavior.
