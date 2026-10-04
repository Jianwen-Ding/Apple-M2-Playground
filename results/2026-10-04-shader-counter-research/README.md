# Selected shader-counter research — 2026-10-04

[Report](../../experiments/timing/shader-counter-candidates.md) distinguishes
API observations, source hypotheses, and missing timer provenance. No justified
shader timer selector/bytes were found; absence in inspected names does not
prove hardware absence. No shader was compiled or executed by this research.

- `egl-inventory.json`, `.stderr`, `.status`, and `egl_inventory.py`: original
  bounded context/timer capability check and reproducer. Three synchronous
  GL timestamp state reads progressed; command timing was not exercised.
- `environment.json`, `source-search.json`: package/vendor revisions, preexisting
  worktree differences and bounded search output.
- `local-manifest.json` and `remote-manifest.json`: original full-source snapshot
  hashes, paths/URLs, timestamps and retrieval failures. Full bulk snapshots
  remain regenerable scratch artifacts; these manifests are historical provenance.
- `source-excerpts.json`: selected lines from hash-verified original snapshots,
  including complete named SR maps, selector packing, helper/register uses,
  firmware timestamp copying, disabled shader-clock support, the compute offset
  mismatch, and constant-zero disjoint getter. These describe source, not exact
  installed binary behavior or measured hardware timer semantics.
- `khronos-timer.txt`: retained primary GLES extension specification with retrieval
  provenance in the remote manifest.
- `verification.json`: original source/API verification, with original report hash.
  `integration-verification.json`: snapshot hashes and selected artifact checks.
  `retained-manifest.json`: selected-file hashes.

The report's raw command timestamp experiment remains planned. P2 now establishes
GLES compute/readback, but a direct timestamp submission backend still requires
separate validation. Ongoing timer experiments are outside this integration.
