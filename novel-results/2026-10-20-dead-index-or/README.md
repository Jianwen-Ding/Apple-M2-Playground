# Stopped lanes no longer contribute to the shuffle index OR

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**256 variants / 768 dispatches with exact controls, zero faults.**

`simd_shuffle` combines the low two index bits across each source quad. Masked
**living** lanes contribute, as the earlier
[sparse-mask shuffle experiment](../2026-10-20-shfl-mask/README.md) showed.
Stopped lanes no longer contribute. This distinction matters separately from
[the stopped-source self fallback](../2026-10-20-stopped-shuffle-index/README.md).

Seed index register r15 uniformly in all physical lanes, then stop alternating
depth-0 lanes. Pop once so every survivor is active. Surviving lanes update
r15 to a new uniform target; stopped lanes cannot execute that update and
retain their known seed bits. Compare immediate and register-index shuffles
of initialized unique lane-ID payloads. All 32 targets, all four possible low
seed values and both alternating masks are tested. Before termination, both
forms also record the original seeded source. Final four-pop markers verify
persistent absence of stopped lanes.

Every register-index output equals the immediate form for the new target,
including self fallback when that target is stopped. Retaining stopped lanes'
seed in the low-bit OR predicts different complete outputs in a subset of
cases; those predictions fail. For example, rotation 0, seed 3, new target 0:
retained seed would select living source lane 3, but hardware returns each
issuing lane's own ID, consistent with target 0 being stopped. With rotation
1, target 0 is living: hardware returns its ID instead of a stopped-source
fallback. These complementary cases were inspected before the full matrix.

Exact wait controls replace only STOP and update every lane's index. Each
complete actual shader is gated against the current simulator's explicit
retained-bit/source hypothesis before hardware. Independent full-buffer
oracles verify both snapshots, immediate/register equality, inputs, guards,
main output and final markers. All before/after controls and recovery
metadata pass, with watchdog/kernel/memory diagnostics retained. No fault or
hang occurred.

This completes the two observed source-liveness rules for this form: exclude
stopped lanes from the source quad's low-index OR, and return the issuing
lane's own A value when the selected source has stopped. Living masked lanes
still contribute their index bits and remain readable. Other shuffle forms
and register-storage behavior of terminated lanes remain separate questions.
The matrix uses full physical groups with alternating stop masks; no timing
claim is made.

```sh
python3 -B scripts/probe_dead_index_or.py --rotate 0 --seed 3 --index 0 --hardware
make verify-dead-index-or
```

[Full evidence](../../results/2026-10-20-dead-index-or/README.md).
