# Preliminary push-overflow mismatch: first shuffle readback

2026-10-20, M2 Max G14C B1, recorded AC-online 0. Low-31 push1 with both
synchronized and stale execution matches the simulator exactly. The first
high-boundary push1 case completes, recovers, and has **one mismatching word**.
These are three programs / nine dispatches, all exact controls, zero faults
or hangs. Matrix expansion is paused for diagnosis, not hardware recovery.

`push-overflow-m65535-n1-synced-r0.json.gz` retains the original counterexample.
After push1, the masked source at lane 12 (original 0xffff) is read as zero
and becomes a writer. The first post-push shuffle reads source 0 (counter
zero), but lane 12 stores **0x40** instead of the simulated/scalar zero at
table word **2188**. All remaining words, including later source reads,
post-pop0/post-pop1 snapshots and final all-lane completion, match. This does
not yet establish an increment/mask semantic correction or pipeline hazard.

Source versions are preserved by hash in `source-versions`. The n0 assembler
canonical alias was fixed from push0 to `update_exec r0l` after the first
low-depth record; this changes no n1 candidate bytes. Thirty-two actual/control
whole-program simulator gates pass. The high-width record's original failed
classification is preserved. Before adding it to an exact aggregate replay,
explain its first-word discrepancy independently and retain any model limit.

Next: isolated padding, initialized destination seeds, source/destination width
and payload-source controls. Each uses the bounded complete program, no
unknown target, no loop/barrier, exact recovery and independent readback oracle.

The [first-shuffle diagnostic follow-up](../2026-10-20-overflow-first-shuffle/README.md)
now preserves 20 additional programs, 60 dispatches, zero faults and exact
controls. Destination seeds show retention; wait0/pop0/duplicate-shuffle
controls distinguish it. The combined 23-program verifier and diagnostic
manifest retain 15 explicit simulator counterexamples, without changing the
earlier exact corpus or fitting a premature timing rule.
