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
