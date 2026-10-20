# Indirect-call winner and global link scope

66 `call-winner-*.json.gz` records and eight `call-link-*.json.gz` records.
Each retains exact shader and known-op control bytes, complete initialized
inputs and readbacks, uniform-call and forced-jump programs/gates, actual
simulator rejection/prediction, decoded boundaries, provenance hashes,
firmware samples, kernel/memory snapshots and exact recovery status.

Eight 32-word planes plus 16 untouched guards: target address, active bit,
pre-marker, callee-entry marker, entry-time link, post-pop callee marker,
fallthrough marker, and post-pop snapshot. The last plane is r0l in the winner
matrix and r1 in the link-scope follow-up. The independent 64-word main output
remains untouched with its patterned tail.

`make verify-call-winner` rebuilds each exact program, re-gates every surrogate,
checks retained diagnostics separately and compares every hardware word with
an independent entry/link/mask oracle. No GPU is used. The supported-model
post-pop link counterexample remains explicit; the other unknown cases retain
their actual-model rejection. Direct DRM uses the adjacent simulator's
`tests/drm_compute.c` through the shared unsafe watchdog's `run_bench` import.
See the [finding](../../novel-results/2026-10-20-call-winner/README.md).
