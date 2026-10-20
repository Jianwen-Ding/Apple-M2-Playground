# Call source/link register alias evidence

Two `call-r1-*.json.gz` initial cases and eleven `call-r1-link-*.json.gz`
fallback snapshots. Each record retains exact code/control/table, original
simulator prediction/gates, complete hardware output, provenance, firmware,
kernel/memory diagnostics and exact recovery controls. All thirteen complete
normally but disagree with the original-target simulator hypothesis.

Table layout is the parent call-winner's eight planes. The final plane is
unused at fallback in the initial cases, and holds post-pop r1 in the eleven
snapshot variants. The 16-word guard suffix and separate main output
remain untouched. Snapshot controls replace only the two-byte call with wait;
they prove r1 contains the original targets before the call's side effects.
Nine records also contain an exact six-byte link-write/fallthrough surrogate.

`source-before-model/` holds hash-addressed builder versions from before model
correction, including the snapshot runner before/after its refined surrogate.
`make verify-call-r1` checks source provenance, every byte/input, all guarded
readbacks and the known model counterexamples without GPU access.
The C harness comes from the adjacent simulator through the shared watchdog.
See the [finding](../../novel-results/2026-10-20-call-r1/README.md).
