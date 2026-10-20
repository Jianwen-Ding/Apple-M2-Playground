# Scattered-mask transfer records

248 compressed records: ret/call × first active 1..31 × target A/B × mask seeds
211/701. Each preserves exact program/control bytes, initialized sparse table,
all re-gated surrogate programs, actual-model result, decoded boundaries,
hardware readbacks, firmware, source hashes, kernel/memory and recovery state.

Return table layout is inherited from `2026-10-20-ret-winner`; call layout is
`2026-10-20-call-winner` with the final plane holding post-pop r1. Program bytes
are unchanged. Inputs differ only in the active-bit plane. Short suffixes can
repeat across seeds; the k=30/31 edge controls have no possible interior hole.

`make verify-sparse-control` reconstructs every program/input and exact sparse
surrogate gate, then independently checks membership and every hardware word.
No GPU is used. As in the parent probes, the shared watchdog imports the
adjacent simulator's `tests/drm_compute.c` direct-DRM harness.
See the [finding](../../novel-results/2026-10-20-sparse-control/README.md).
