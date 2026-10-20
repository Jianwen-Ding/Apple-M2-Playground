# Return reactivation and stop model integration

Simulator commit **d90cdcd** corrects two coupled mask behaviors measured on
M2 Max G14C B1. The opt-in return model now applies `0 -> 2, 1 -> 0, deeper
unchanged` to live lanes when the issuing mask is nonempty. An empty-issued
return keeps its early fallthrough without touching mask counters. Stop ends
issuing lanes and permits masked survivors to continue; an empty stop is a
no-op. Persistent physical liveness prevents mask operations from reviving
stopped or nonexistent lanes, including partial workgroups and preambles.

The return rule remains behind `AGX_EXPERIMENTAL_RET=buffer-pop2`. The stop
correction applies in default mode too. Existing return/register-call refusal,
link alias ordering and target bounds/alignment checks remain intact. The
legacy `AGX_EXPERIMENTAL_RET=1` mode remains a contradicted offline hypothesis.
Counter values for masked lanes are an operational representation inferred
from pop thresholds; this change makes no claim about reading terminated-lane
register storage or call/return timing.

Hardware basis:

- [Empty/partial stop](../../novel-results/2026-10-20-empty-stop/README.md):
  17 programs including return/stop context, 51 dispatches.
- [Return arrival/depth](../../novel-results/2026-10-20-ret-mask-state/README.md):
  36 pre-pop and 21 depth cases, 171 dispatches, depths through four.
- [Empty-issued return](../../novel-results/2026-10-20-empty-ret-state/README.md):
  16 programs, 48 dispatches, known-state and exact wait controls.

No new hardware was needed for integration. `model-replay.json` binds source
hashes for all three modified simulator files, the actual binary digest and
every retained evidence-file digest. It replays **570 original shader/input
pairs directly**, comparing complete main/table readbacks, without calling a
probe builder or submitting to the GPU. This includes the earlier 480
winner/link/alias/three-target programs and 90 return/stop-state programs.
The six original stop and 45 return-state simulator counterexamples now pass.

Independent target verifiers still reconstruct shader bytes, resolve recorded
builder hashes and check hardware against scalar output oracles. Before
updating any builder gate, preserve its original source as a hash-addressed
`.py.txt` under `ret-prepop/source-before-model/`; the original hardware records
and rejected hypotheses remain unchanged. The current builders demand exact
simulation of each actual program before any hardware submission.

Validation: 40 Rust library tests pass; all 721 retained suite cases pass
exactly in default mode. The 23 control-suite and 75 control-coverage cases
pass with both default settings and the measured return model. Playground
`verify-empty-stop`, `verify-ret-mask-state`, `verify-empty-ret-state`,
`verify-control-model` and historical `verify-call-ret` checks pass.

Unmeasured follow-ups include deeper counters, direct reads of masked counters,
permanent termination through more control operations and nested divergent
calls. This model is functional; timing remains uncalibrated.
