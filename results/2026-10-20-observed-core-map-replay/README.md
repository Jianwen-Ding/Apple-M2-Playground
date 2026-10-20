# Observed core-map replay evidence

`make verify-observed-core-map-replay` uses no GPU. It checks the 160 geometry
records against their committed digests, regenerates exact shader/control
bytes, independently checks every arithmetic/guard/tag plane and all 320
recovery buffers, then executes the recorded programs in the functional model.

All 80 SR20 records are replayed with a map extracted only after every lane's
tag and workgroup uniformity have been validated. Complete outputs and tables
match the retained hardware buffers literally. The other 80 SR19 records
match independent literal expectations. All 64 unique default program/launch
cases execute in both archived and current simulators and must match complete
buffers, JSON statistics and independent scalar/default-placement oracles.

`analysis.json` binds every raw record, complete replay-readback digest,
canonical JSON core-map digest, default result and statistics, source version,
historical model and new replay binary. The original geometry analysis and
all raw data remain unchanged. `recorded-model.json` identifies the historical
source commit and the exact binary archived under scratch before rebuilding
`agx_run`. That archived binary is required for the direct version comparison;
its fingerprint must equal the recorded geometry checker. Scratch is persistent
in this workspace; the historical source commit is retained in git.

The seven ordinary arithmetic verifiers now distinguish the frozen recorded
fingerprint in `scripts/integer_recorded_model.py` from the current model they
execute. They still check exact historical provenance and current independent
oracles. New reports expose both versions, rather than requiring different
model versions to have identical bytes. The frozen fingerprint applies to
these closed corpora; future hardware evidence must record its own checker.

The simulator's three `m2_core_map` library tests check per-lane SR20 injection,
unchanged default/synthetic core and slot values, wrong length, disabled IDs,
mixed blocks, no writes after rejection, a valid partial tail and the scope
of 1-D block validation. The replay verifier adds five CLI error cases and
checks they occur before preamble execution or dump replacement.

[Implementation behavior and limits](../../novel-results/2026-10-20-observed-core-map-replay/README.md).

`regression-summary.json` records the successful seven-target make invocation,
current verifier/model fingerprints and unchanged baseline digests: 405 records
covering 19821 prior completed submissions. It records zero new hardware
submissions. Every target was run against the current functional binary.
