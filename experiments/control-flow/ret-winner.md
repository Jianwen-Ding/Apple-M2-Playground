# Return winner with lane 0 excluded and divergent active operands

Question before hardware (2026-10-20): does a register return select the lowest
active lane's target when active lanes disagree and physical lane 0 is masked?
The previous lane0out test had all active lanes agreeing, so it cannot settle
this case. The functional simulator deliberately rejects it.

Set each target to one of two valid decoded landing blocks. Mask lanes below k,
put target B in lane k alone and A in every other lane, including inactive
lane 0. The lowest-active hypothesis predicts B; stale-lane-0 and majority
hypotheses predict A for k < 31. Swap A/B to distinguish a target-address bias.
At each landing pop once and record a tag, then pop again and record another:
this also checks the active/deferred lane split without stop padding before
the pops. Every input, output slot and address is initialized before masking.

First run k=31 (one active lane, existing uniform-active simulator support),
then k=1. Before each hardware variant, validate both landing paths using
uniform-return operand substitutions and direct-jump substitutions. For k<31
retain the actual simulator's unsupported diagnostic. These substitutions gate
bounded surrounding code and both outcomes, not the unmeasured winner rule.

Use the bounded unsafe watchdog with exact known-operation jump controls
before/after, complete readbacks/guards, kernel and memory snapshots. Stop GPU
submissions if recovery fails or the process remains blocked. Preserve/push
any fault and choose further bounded hypotheses only after a passing recovery.
Runner: `scripts/probe_ret_winner.py --first K [--winner A|B] [--hardware]`.
