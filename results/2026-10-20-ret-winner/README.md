# Lowest-active return winner records

64 compressed records: k=1..31 × targets A/B, plus two k=1 repeats. Each
retains exact shader/control bytes, initialized table, both uniform-return
and jump surrogate programs and gates, actual simulator diagnostic, decoded
boundaries, complete variant/control readbacks, firmware, kernel/memory
snapshots, provenance hashes and recovery status.

Table planes (32 words each): per-lane target, active bit, pre-marker, landing
marker after pop 1, landing marker after pop 2, fallback marker, final r0l.
A 16-word suffix stays untouched. The separate 64-word main output remains
entirely guarded with its 16-word patterned tail.

`make verify-ret-winner` reconstructs every exact shader/input, replays all
four surrogates per record, checks the actual unsupported diagnostic separately
and checks every retained hardware word using independent membership sets.
No GPU is used. The direct-DRM harness is the adjacent simulator's
`tests/drm_compute.c`, imported by the shared unsafe watchdog via `run_bench`.
See the [finding](../../novel-results/2026-10-20-ret-winner/README.md).
