# Retained G14C B1 multiply-add addend observation

The [experiment report](../../experiments/arithmetic/imadd-addend.md) describes
the hypothesis, exact one-bit edit, observed outputs and limits. This directory
preserves the passing run at
`/scratch/apple-m2-playground/agx-imadd-addend-runs/20261004T225032918936Z`.
Regenerable executables stay in scratch. All shader/readback bytes necessary
for offline verification are retained as hex.

- `record.json`: original runner record, full six-case oracles/API events,
  pinned driver, dependency and source hashes.
- `patch.json` and `imadd-patch/`: exact input/patched/stale shader bytes,
  digests, fields and main/preamble disassembly.
- `*.readback.hex` and `*-oracle.json`: raw little-endian readbacks and original
  comparisons, including all guards, padding and tail.
- Named child directories: original stdout/stderr and command status/bounds.
- `sources/`: unchanged snapshots from the hardware run. The integrated patcher
  additionally checks imported module origins and corrects a field-layout comment;
  historical snapshots remain intact.
- `environment.json`: explicitly labeled integration-time kernel capture;
  hardware-run identity remains in the original API logs.
- `integration-verification.txt`: independently recomputed checks, including
  software-only tamper discrimination. `manifest-sha256.json` hashes retained files.

Run `make verify-imadd` from the repository to verify committed evidence without
GPU access or the historical scratch run. Patcher tests require the pinned vendor
applegpu checkout; the independent stored-evidence verifier uses only Python's
standard library. Run `make agx-imadd` separately for hardware reproduction.

Kimi K3 implemented the patcher/runner and executed the hardware suite via
`acm-dev`. GLM 5.3 implemented an independent verifier and checked the scratch
run. Both provider sessions terminated during final packaging (access/funding
errors). The coordinator completed documentation, hex retention and verification;
no final independent-agent report is claimed. Native Claude/Grok launch failures
and Gemini authentication failures produced no experiment evidence.

This validates one known immediate addend field in one shader. It does not
establish a novel opcode, general arithmetic semantics or timing behavior.
