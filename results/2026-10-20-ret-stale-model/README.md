# Conditional RET counter/execution model integration

Simulator **c7e50f7** corrects a distinction exposed by ordinary r0 writes:
nonempty RET updates counter 0 to masked depth 2 and counter 1 to active zero;
deeper live counters retain **both** their stored value and current execution
bit. It no longer assigns depth 2 to every cached issue-active lane. Ordinary
writes can make those two models diverge. Target selection still uses the
lowest issuing lane before updates; empty-issued RET falls through unchanged.
Dead lanes stay dead, and default opt-in/target guards remain intact.

[Thirty-four hardware programs](../../novel-results/2026-10-20-ret-stale-exec/README.md)
separate stored depth from stale execution across half/full moves, half add
and immediate writes, mixed/uniform depths through 31. Every actual shader
first passed its explicitly recorded old issue-based hypothesis. Independent
IF/jump controls construct known depth 2 without RET/r0 writes and pass before
and after every candidate. All 102 dispatches completed with exact controls,
zero faults and retained watchdog/kernel/memory recovery metadata.

The first mixed case's original all-false hypothesis classification remains
unchanged; an independent oracle explains every readback word with the refined
rule. Initial source versions are archived by hash before classification/gate
changes. All original records and rejected diagnostics remain preserved.
Current builders demand exact measured-program simulation before submission.

`model-replay.json` binds binary/source hashes and all **2,277 original control
evidence-file digests**. It replays saved shader/input bytes directly, without
regenerating shaders or accessing the GPU. Every complete main/table buffer
matches, including all 34 corrected counterexamples and prior return/stop,
shuffle liveness, ordinary-write/pop0 and balanced-nesting families.

Validation: all 42 Rust library tests pass; the 23 control-suite and 75 control-
coverage cases pass with both default settings and return opt-in. Independent
stale-RET, return-depth, empty-return, ordinary-write, pop0 and historical
call/return verifiers pass. Existing empty-issue behavior and all earlier
balanced-call examples remain exact. Timing is not calibrated.

Stale-mask target disagreement, already-masked ordinary writes, larger counter
values and other mask operations remain separate hardware questions. The
uniform valid r30 targets here do not establish new target-selection semantics.
