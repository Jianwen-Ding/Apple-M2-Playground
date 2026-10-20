# Relative, xor and rotate shuffles exclude stopped index bits

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**320 variants / 960 dispatches with exact controls, zero faults.**

Stopped lanes no longer contribute to the source quad's low-index OR for
native `simd_shuffle_down`, `simd_shuffle_up`, `simd_shuffle_xor` and
`simd_shuffle_rotate_up`. Masked living sources remain readable, while a
selected stopped source [self-fallbacks](../2026-10-20-stopped-native-shuffle/README.md).
Together these independently measured rules extend the
[plain-shuffle finding](../2026-10-20-dead-index-or/README.md).

Initialize unique lane-ID payloads and uniform index r15 in all physical lanes.
Stop alternating depth-0 lanes, pop once and let every surviving lane update
r15 to a new offset. Stopped lanes retain their known old low bits. Gather with
immediate and register forms, before STOP and after the update. The matrix
covers both masks, all four initial low-bit seeds, ten offsets
(0,1,2,3,4,7,8,15,16,31) and all four forms. Final four-pop markers independently
check persistent absence of stopped lanes.

All register-index outputs equal immediate selection using the new surviving
index bits. A separate retained-bit oracle applies the old seed to the source
quad's low rotation/xor, preserving the original offset's quad selection and
up/down bounds. Decisive cases reject it in every form. The initial seed-1,
offset-2 case for each form was inspected before extending the matrix.

Exact wait controls retain every lane and update all indices. Every candidate
and control first passes its explicit current simulator hypothesis. Hardware
full main/table readbacks match independent scalar oracles, including both
snapshots, inactive slots, initialized depths, final markers and guards.
Watchdog/kernel/memory/recovery evidence remains retained. No fault or hang
occurred; every recovery control passed.

Simulator bf03118 still includes stopped index bits and reads stopped sources
for these four forms. The verifier retains those counterexamples explicitly;
original evidence and hypotheses are unchanged. A combined native-form model
correction can now follow, with the earlier plain-shuffle and masked-lane
cases replayed to guard their distinct behavior. Underlying terminated-lane
storage and timing remain unobserved.

```sh
python3 -B scripts/probe_native_dead_index_or.py --kind down --hardware
make verify-native-dead-index-or
```

[Full evidence](../../results/2026-10-20-native-dead-index-or/README.md).

The [native-form simulator correction](../../results/2026-10-20-native-shuffle-model/README.md)
in commit 4dd68e9 now reproduces every original program here. Initial hypotheses,
readbacks and source bytes remain unchanged. Current builders require complete
actual-program equality with the measured model before further submission.
