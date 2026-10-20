# Explicit unsupported overflow activation and retained hypotheses

Simulator **defc29d** detects IF/push increments that wrap a **previously masked
living lane** to counter zero. Its functional activation/spacing behavior is
unresolved. Default execution refuses further work until a directly measured
`wait 0` or `pop_exec r0l, 0` settlement, rather than silently returning the
incorrect immediate-activation prediction. Already-issuing wrap cases remain
supported. Stopped and absent lanes do not generate pending activation.

The guard is deliberately conservative: it also refuses some empirically
sufficient move spacing and other sequences that happen to be exact on the
tested hardware. It does not fit a universal cycle count or instruction-
spacing rule from the limited matrix. Other wait slots, nonzero pops or
unmeasured mask operations are not guessed as settlement of this pending state.
This guards the model's supported scope; it does not implement the pipeline.

`AGX_EXPERIMENTAL_EXEC_OVERFLOW=counter-sync` explicitly preserves the old,
known-incomplete immediate-sync hypothesis for offline comparison and bounded
experiments. The new `overflow_hypothesis.py` context and metadata name that
hypothesis instead of labelling it hardware-accurate measured execution.
Original probe source versions, hardware bytes and failed classifications
remain unchanged and resolve by hash. Future gates pin the hypothesis helper.

`guarded-replay.json` replays all **54 original overflow programs** directly
from saved shader/input bytes, without regeneration or GPU access:

| Mode | Exact accepted programs | Explicit refusals | Retained hardware mismatches |
| --- | --- | --- | --- |
| Default guarded model | 11 | 43 | 0 accepted |
| Explicit counter-sync hypothesis | 19 | 0 | 35 |

The 43 refusals include all 35 known counterexamples and eight hardware-exact
programs whose unmodelled spacing is conservatively refused. Every independent
control still matches under default settings. All 162 original dispatches
completed with exact recovery controls and zero faults; no new GPU work was
needed for this integration.

`control-model-replay.json` binds all **2,403 earlier exact control-program
digests**, current binary and five relevant source hashes, including the
functional `fsem.rs` mask path. Every full main/table buffer remains exact.
Historical replay manifests are preserved rather than rewritten.

All **44 library tests** pass. New fixtures cover reference, compiled and
functional mask execution, n1/n2/n3, default rejection before destination
mutation, wait0/pop0 settlement, already-issuing overflow, dead lanes and the
explicit hypothesis. The functional mask path now observes the same persistent
live-lane checks as the other two executors. Both the 23 control-suite and 75
control-coverage cases pass with default and return-opt-in settings. Independent
overflow trace/visibility verifiers still require all original counterexamples.

```sh
make verify-overflow-guard
make verify-overflow-first-shuffle verify-overflow-register-visibility
```

[Observed spacing scope](../../novel-results/2026-10-20-overflow-register-visibility/README.md).
Next: distinguish lane sequencing, code alignment and mask/update latency
before implementing a physical timing model. No calibrated cycle value is
claimed by this guard.
