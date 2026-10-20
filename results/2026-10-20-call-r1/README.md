# Call source/link register alias evidence

Two `call-r1-*.json.gz` initial cases and eleven `call-r1-link-*.json.gz`
fallback snapshots, plus nine `call-r1-mask-*.json.gz` pre-pop participation
checkpoints. Each record retains exact code/control/table, original
simulator prediction/gates, complete hardware output, provenance, firmware,
kernel/memory diagnostics and exact recovery controls. All twenty-two complete
normally but disagreed with the original-target simulator hypothesis.

Table layout is the parent call-winner's eight planes. The final plane is
unused at fallback in the initial cases, and holds post-pop r1 in the twenty
snapshot variants. The 16-word guard suffix and separate main output
remain untouched. Snapshot controls replace only the two-byte call with wait;
they prove r1 contains the original targets before the call's side effects.
Eighteen records also contain an exact six-byte link-write/fallthrough surrogate.

`source-before-model/` holds hash-addressed builder versions from before model
correction, including the snapshot runner before/after its refined surrogate.
`make verify-call-r1` checks source provenance, every byte/input, all guarded
readbacks and exact corrected-model replays without GPU access. Original model
counterexamples retain their source provenance. `model-replay.json` hashes
all 408 original cases and the corrected simulator source/binary.
The C harness comes from the adjacent simulator through the shared watchdog.
See the [finding](../../novel-results/2026-10-20-call-r1/README.md).

The pre-pop variants use a distinct marker in the callee-entry plane before
reconvergence. Only original issue-active lanes write it. Every address and
byte count remains fixed by removing 16 bytes of stop padding before callee A.

The corrected simulator (`d66f359`) replays every original byte/input/readback
case exactly. Current builders require actual-program equality. The archived
versions and original records preserve the rejected consume-before-write
hypothesis; the evidence has not been rewritten to match the new model.
