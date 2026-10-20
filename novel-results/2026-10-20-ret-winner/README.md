# A divergent return selects the lowest active lane's target

Confirmed in the tested scope on M2 Max G14C B1, compute, direct DRM, AC power,
2026-10-20. **64 variants / 192 dispatches including controls, zero faults.**
This resolves the case the current functional simulator deliberately rejects:
active return operands disagree while physical lane 0 is inactive.

For every k=1..31, mask lanes 0..k-1. Give lane k target B and every other lane
(including inactive lane 0) target A; then swap A/B. Both targets are valid
in-program landing instructions. For k<31, the lowest active lane disagrees
with every other active lane and inactive lane 0. At k=31 the single active
lane supplies the already modelled uniform-active control. Repeat k=1 in both
directions.

**Every variant lands at lane k's target.** There is no fixed address bias,
majority selection or stale-lane-0 selection in this matrix. All lanes execute
the winning landing's continuation: pop 1 activates only the previously
inactive prefix 0..k-1, and pop 2 activates everyone. Disagreeing active lanes
do not execute a different landing or the fallthrough block. This extends the
[earlier return observations](../2026-10-17-call-ret/README.md), whose lane0out
case had all active lanes agreeing and did not decide this question.

The first landing instruction is `pop_exec`, with no intervening stops. This
keeps the separate [return/stop context issue](../2026-10-20-empty-stop/README.md)
out of the winner experiment. Nothing here establishes arbitrary/invalid
return-address behavior, inter-group ordering, function-call target selection,
or a general hidden return-state model. The active sets tested are contiguous
suffixes; scattered active masks and more than two candidate addresses remain
follow-ups.

## Gate and evidence

Each exact shader is decoded completely, both destinations are checked against
instruction boundaries, and all inputs and trace indices are initialized
before masking. Save original global ID before any transfer and index every
slot with that saved register.

For each shader, two substitutions change only the return operand and a
uniform target initialization, exercising uniform-return paths A/B with the
same partial mask. Two direct-jump substitutions independently validate each
landing. Every surrogate matches a full-buffer host oracle in `agx_run`.
The actual divergent shader's rejection is retained for 62 cases; the two
single-active variants simulate exactly. No guard was removed to submit the
unmodelled cases. The known-operation jump-A program supplies exact hardware
controls before and after each variant.

All hardware words, guards, untouched inputs, fallback slots and landing
membership sets match an independent checker. The watchdog retains kernel,
firmware and memory diagnostics; no fault/timeout or failed recovery occurred.
The simulator's winner rule has not yet been extended; its unsupported status
is explicit rather than presenting surrogate checks as complete simulation.

```sh
python3 -B scripts/probe_ret_winner.py --first 31             # uniform-active gate
python3 -B scripts/probe_ret_winner.py --first 1 --winner B   # both outcomes gated; actual unsupported
python3 -B scripts/probe_ret_winner.py --first 1 --winner B --hardware
make verify-ret-winner
```

Use `--repeat N` to avoid overwriting a previous hardware record.
[Retained evidence](../../results/2026-10-20-ret-winner/README.md).
