# Empty-mask stop at mixed execution depths

Question, 2026-10-20: the experimental return model currently assumes that a
`stop` issued with no active lane kills depth-1 lanes if any other lane has
depth >= 2. Is that effect real when isolated from calls, returns and padding?

Hypothesis: with odd lanes at depth 1 and even lanes at depth 2, `stop`, then
three `pop_exec ..., 1` checkpoints should never reactivate the odd lanes if
the model is right. A matching `wait 0` control must reactivate odd lanes after
one pop and everyone after two. The competing hypothesis is a masked no-op:
stop and wait then produce identical lane/checkpoint traces. Full depth-1,
depth-2 and depth-3 masks and a partially active stop distinguish other cases.

The probe uses one full SIMD group, no calls, returns, branches, loops,
barriers or uninitialized values. Every trace address is prepared before any
masking. A prefix marker and a partially active checkpoint precede the empty
mask; markers follow each of three pops, with a final visible r0l snapshot.
The scalar mask-depth oracle and the exact program run in the simulator with
`AGX_EXPERIMENTAL_RET=buffer-pop2` before hardware. A simulator match is a
validation of the hypothesis and surrounding code, not hardware confirmation.

Start with `probe_empty_stop.py mix12` offline, then `--hardware`. The shared
`probe_control_followup.hardware()` records exact before/after controls, all
readback/guards, source and simulator hashes, kernel-log deltas, power, memory
and timeout diagnostics. A recovered fault permits a different bounded follow-up
after its exact recovery control passes. A blocked host process or failed
recovery control ends GPU submissions; retain and push its evidence promptly.
