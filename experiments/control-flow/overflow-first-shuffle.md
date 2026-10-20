# Isolate the first read after overflow reactivation

2026-10-20, after preserving the one-word push1 counterexample. Repeat its
exact bytes in a separately named record before changing anything. Then vary
one detail: 1/2/4 waits after push, a harmless ALU instruction, explicit pop0,
integer true IF instead of float true IF, initialized destination seed before
divergence, or first shuffle using ordinary payload/half registers.

All original low-counter/payload full-buffer expectations remain identical:
source 0's original and updated value are both zero; only its first shuffle
instruction is substituted for width/payload controls. Inputs, output guards,
remaining snapshots and the fully unrolled bounded drain are unchanged. Every
complete modified program must decode and match simulation before submission.
The original failed hardware record/classification remains unchanged. This
is hypothesis isolation, not evidence for a pipeline rule before readbacks.

Each case retains pre/post controls, watchdog/partial data and kernel/memory/
power/boot state. Inspect each outcome before the next chosen discriminator.
No loops, barriers or invalid addresses. A blocked process/failed recovery
prevents further GPU submissions; clean mismatch is analyzed rather than
called a hang. Broader overflow n2/n3/rotation expansion remains pending.

Outcome: 20 selected diagnostic programs plus the three base cases, 69
dispatches, zero faults/hangs, all controls exact. The immediate first-shuffle
destination retention repeats across n1/n2/n3, all native forms, half/payload
sources, integer IF and a lane rotation. Destination seeds survive into the
bad result. Wait0, pop0 or a second shuffle makes the tested complete program
exact; one intervening ordinary ALU instruction does not. The already-issuing
case is exact. Fifteen simulator counterexamples are retained explicitly;
broader generalization and masked-destination reads remain pending.
[Report](../../novel-results/2026-10-20-overflow-first-shuffle/README.md).
