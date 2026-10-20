# Prepared-index overflow destination evidence

The 27 gzip records bind exact input and actual/control programs, source and
simulator hashes, instruction boundaries, prepared-output-index metadata,
complete main/table readbacks, firmware timestamps, watchdog/kernel/memory,
power and boot state, and exact pre/post recovery controls. All 81 dispatches
completed; event counts stay zero, boot is unchanged and recorded AC-online 0.

`make verify-overflow-register-visibility` checks every byte/input, independently
computes all expected masks and buffers, and verifies the observed destination
retention in its exact measured matrix. It checks the direct store immediately
after the first opcode, the after-wait/after-drain captures, seed/prepared
addresses and untouched guards. The retained observations are not treated as
a universal timing rule. Historical builder versions resolve by source hash.

`model-diagnostic-replay.json` binds all 27 evidence-file digests plus the
binary/source hashes. It explicitly records **10 exact model cases and 17
model counterexamples**, including their affected destination lanes. The
older exact corpus is unchanged. The source-only immediate-assembly fix uses
the existing canonical full-immediate encoder and changes no earlier shuffle
candidate bytes. No hardware record or original classification was rewritten.

[Interpretation, spacing matrix and limits](../../novel-results/2026-10-20-overflow-register-visibility/README.md).
