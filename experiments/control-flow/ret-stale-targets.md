# RET target selection with stale execution

2026-10-20, plan before hardware. Existing ordinary-write/RET probes use one
uniform target and cannot establish divergent target selection when stored
counters disagree with execution. Seed initialized targets for all 32 lanes,
create a suffix/scattered IF mask, write depths only in its issuers without
pop0, then return. Pair a known IF/jump control without RET or ordinary r0
writes. Check every prefix payload and all three landing snapshots/counters.

Three distinct decoded in-program destinations and the fallthrough each have
three snapshots followed by 12 unrolled pop3 operations and a final all-lane
marker/zero-counter store. All source/index registers are initialized before
use. Maximum stored depth is 31. No loop, invalid target or barrier is used.
Actual/control full-program simulation and independent scalar full-buffer
oracles must pass before hardware. The current measured hypothesis chooses
the lowest cached issuer before the conditional stored-counter RET update.
Competing zero-counter and after-update target hypotheses are recorded.

Start with full-mask deep-first, then zero-first; inspect exact buffers and
recovery before partial masks and uniform patterns. Rotate the three target
labels only after selection is understood. Preserve partial data, timestamps,
kernel/memory state and recovery controls. Any mismatch stops matrix expansion
for analysis. Established recovery is required after a fault; blocked host
process or failed control prevents further GPU submissions. No hang is assumed.

Outcome: all 90 programs / 270 dispatches exact, zero faults or hangs. RET
selects the lowest cached issuer before conditional counter updates; 60 cases
distinguish zero counters, 66 after-update participation, 36 both. Prefixes,
three landing snapshots, final drain and independent controls all match.
[Evidence and independent verification](../../novel-results/2026-10-20-ret-stale-targets/README.md).
