# Matched immediate-add timing

2026-10-20, before hardware. Calibration uses immediate 1 and the recent chain
studies used 3. Both encode as eight-byte iadd instructions, differing only
in the immediate field. Compare these small positive values with identical
registers, code length, add count and launches; retain every timing sample.

First run a 32-lane, 64-add, four-repetition pilot for each value. Require
complete scalar/simulator agreement and exact bracketing recovery controls.
Then prepare all full-program gates before measuring: 131072 lanes, 128-lane
workgroups, 64 register halves, 1/8 chains, 1024/2048 adds, 64 consecutive
submissions, three deterministically interleaved trials per cell. One GPU
worker holds the same nonblocking lock as the preceding train study.

Every shader seeds registers anew, with output-only tables. Verify simulation
from initial and previous output tables. Preserve full final buffers, guards,
waits, repeat indices, completion markers, firmware times, source provenance
and kernel/memory/power/recovery diagnostics. Intermediate buffers are not
captured. A blocked process or failed recovery prevents further submissions.
No cost adjustment follows without identifying an explanatory effect.

Completed: 26 trains / 1596 dispatches, exact final buffers and 52 recovery
controls, zero faults. Eight-chain timing barely changes between values;
one-chain identical programs exhibit large trial-to-trial timing variation.
See the [finding](../../novel-results/2026-10-20-integer-immediate-cost/README.md).
