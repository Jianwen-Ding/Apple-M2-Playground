# Functional shuffle source-liveness integration

Simulator **bf03118** implements the two measured `simd_shuffle` rules:
exclude stopped lanes from each source quad's low-index OR, and return the
issuing lane's own A value when the selected physical source is stopped.
Masked living lanes still contribute low index bits and remain readable.
Both the compiled and descriptor interpreter paths apply these rules.
Other native shuffle forms are unchanged pending separate measurement.

Hardware basis: [nine stopped-source gathers](../../novel-results/2026-10-20-stopped-r0/README.md),
[256 paired immediate/register source cases](../../novel-results/2026-10-20-stopped-shuffle-index/README.md)
and [256 index-contribution cases](../../novel-results/2026-10-20-dead-index-or/README.md).
All were gated against explicit pre-change hypotheses and surrounded by exact
controls before hardware submission; initial diagnostic cases were inspected
before extending each matrix. These 521 programs required 1,563 dispatches,
all with exact controls and zero faults. The two matrices independently
separate source-liveness effects from register-index contamination.

Nine initial gathers, 82 paired-source cases and 184 index-contribution cases
contradicted the previous simulator: **275 counterexamples**, all now exact.
Original compressed evidence and source versions remain preserved. Before
updating builder gates, their exact source bytes were archived by hash under
`stopped-r0/source-before-model/`; provenance resolution includes that archive.
Current builders require complete actual-program simulation of measured rules.
Target verifiers continue independently checking every main/table word and
resolving recorded source hashes rather than changing historical metadata.

`model-replay.json` binds the actual binary, four relevant source hashes and
all **1,115 original hardware evidence-file digests**. Replay uses saved shader
and input bytes directly, comparing full main/table readbacks with no GPU and
no builder reconstruction. It includes earlier winner/link/return/stop/depth
and masked-counter families. No model-only regenerated shader replaces the
original hardware programs.

Validation:

- All 1,115 original control programs replay exactly.
- Independent stopped-source/index-OR/masked-r0 verifiers pass.
- Earlier sparse-mask/paired-64-bit shuffle verifier passes both seeds,
  including exact positive results and deliberate index-contamination cases.
- All 41 Rust library tests pass, including independent measured fixtures for
  both interpreters that distinguish masking from termination.
- All 23 retained control-suite and 75 control-coverage cases pass with both
  default settings and the opt-in return model.

Persistent liveness was introduced in d90cdcd for per-lane STOP. This change
uses it for shuffles; it does not infer the underlying register contents of a
terminated source. Functional evidence is restricted to the measured native
shuffle form, initialized operands and bounded full physical SIMD groups.
Call/return/shuffle timing calibration and other native shuffle forms remain
follow-ups.
