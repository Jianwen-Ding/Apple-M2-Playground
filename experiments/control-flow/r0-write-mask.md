# Ordinary r0 writes and execution synchronization

2026-10-20, before hardware: all previous r0 observations used dedicated
IF/pop/call/return operations. Does an ordinary ALU write to r0l immediately
change the execution mask? `probe_r0_write_mask.py` begins with all physical
lanes active and initialized per-lane depth payloads. Write via mov-half,
mov-full, add-half or a uniform immediate; record r0/writer membership before
any mask instruction, then after one pop and a longer bounded drain. The
control first copies the same input through an ordinary GPR on all lanes,
constructs known depths with IFs and executes the identical later trace.

Gate the complete candidate against the current simulator's deferred-mask
hypothesis and every control word against an independent oracle. Hardware
classifications separate immediate update, deferred update, ordinary-register-
only writes and ignored writes. Begin mov-half with mixed 0..3, rotation 0,
inspect every buffer and exact recovery before trying other forms or patterns.
All indices are prepared before r0 writes; input lows are initialized and
small; no call/ret/loop/barrier/invalid target/uninitialized source occurs.
Drain depths are bounded before final marker/stop. Retain watchdog/kernel/
memory diagnostics and stop submissions if recovery is not established.

Ordinary writes defer execution updates in all 34 cases. Next `probe_r0_pop0.py`
replaces the first pop1 with pop0. It gates the actual complete shader against
zero-count synchronization, preserving every written counter. Its independent
recovery control replaces that operation with waits after known IF construction,
so control correctness does not assume pop0 behavior. If hardware skips the
zero-count operation, every lane will still store its nonzero counter at the
second checkpoint; true synchronization lets only zero-counter lanes write.
Start mixed mov-half 0..3 and inspect exact recovery before extending forms.
No transfer/loop/barrier is introduced and the known bounded drain remains.

Pop0 zero-membership synchronization is exact in 34 cases. Next isolate RET
with deliberately stale issuing execution using `probe_ret_stale_exec.py`:
ordinary r0 write leaves all lanes active, uniform initialized r30 names one
valid decoded landing, and RET is followed by four membership/r0 snapshots
before a bounded drain. The current simulator predicts every issue-active lane
receives depth 2. A competing raw-counter transform maps 0->2,1->0,>=2 unchanged
independently of stale execution. Separate branch-only, sync-only and empty-
fallthrough hypotheses are retained. A no-RET/no-r0-write IF/jump control
constructs known depth 2 and validates all landing/trace addresses. Gate the
whole actual against the current issue hypothesis before hardware. First
mov-half mixed 0..3 only; inspect complete classification and exact recovery
before any uniform inputs, other forms or matrix. All targets are valid and
all sources/indices initialized; no uninitialized link, loop or barrier occurs.
