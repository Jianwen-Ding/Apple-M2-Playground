# Counter-overflow activation affects ordinary register writes too

M2 Max G14C B1, direct DRM compute, 2026-10-20, recorded AC-online 0.
**27 programs / 81 dispatches**, exact independent controls, zero faults
or hangs. These are functional spacing observations, not calibrated cycles.

The earlier [first-shuffle trace](../2026-10-20-overflow-first-shuffle/README.md)
also depended on post-overflow address calculations. This probe prepares
every output index while all lanes issue and initializes the tested
destination to 0x1234. The first operation after push writes the defined
value 0xbeef. A direct store immediately follows, with no AND or index ALU;
the destination is read again after wait0, then in all lanes after the bounded
drain. This independently separates destination updates from address creation.

An immediate move, ordinary copy and integer add can all leave the old
destination in newly activated overflow lanes. The old value persists after
the wait and final drain, so it is not just a transient value in the first
store. Native shuffle is also affected, with lane dependence in the tested
layout: its lower-half overflow destination stays old while upper-half
destinations get the expected value. A separate high-only lane-31 case is
exact; a layout with overflow lanes 7/15/23/31 retains 7/15 and updates 23/31.
This extends the observed scope beyond a shuffle-only interpretation.

The standard vector repeats depths 0/1/2/3/32767/32768/65532/65533/65534/65535,
truncated to 32 lanes. For push1 its overflow lanes are 9/19/29. Direct
destination traces give this bounded spacing matrix:

| First operation | Intervening initialized scratch moves | Retained overflow destinations |
| --- | --- | --- |
| Immediate move | 0, 1, 2, 4 or 5 | 9, 19, 29 |
| Immediate move | 6 | 19, 29 |
| Immediate move | 7 or 8 | none |
| Native shuffle | 0, 2, 4 or 5 | 9 |
| Native shuffle | 6, 7 or 8 | none |
| Native shuffle | wait0 instead of moves | none |

These counts describe the exact six-byte move sequence and tested layout;
they do not establish cycles, a universal required NOP count, alignment
independence or a full execution-mask pipeline model. The partially updated
six-move immediate case is important evidence against a simple all-or-nothing
one-instruction rule.

Push2 moves the affected lanes to 8/18/28 and push3 to 7/17/27. Immediate
move retains all three in each case; shuffle retains the lower-half lane.
When ordinary counter writes leave all lanes already issue-active before
push, both immediate and shuffle programs are exact. The final all-lane
reads also show newly masked lanes retaining their destination seeds, rather
than being overwritten by these first operations. A low-depth no-overflow
control and the high-boundary wait0 case are exact.

Controls use initialized zero-membership flags with simple IF/wait0, no
ordinary r0 writes and no tested push. Every actual/control whole program
first matches the current explicit functional hypothesis and scalar oracle.
All sources and addresses are prepared in issuing lanes before use, all
accesses stay in the allocated table, and all guards are exact. The largest
shader is 131,412 bytes, using the previously measured unrolled pop3 drain;
there are no branches, loops, barriers or invalid targets.

The independent verifier preserves **10 model matches and 17 counterexamples**.
Together with the earlier base/diagnostic family there are **35 explicit
counterexamples in 54 programs / 162 dispatches**, all recovered, zero faults.
The older 2,403-program exact corpus remains separate. The current simulator
does not implement this activation/spacing effect; the evidence must not be
silently counted as exact. Mask-operation latency, lane sequencing and code
alignment need further discrimination before a general functional/timing model.

```sh
python3 -B scripts/probe_overflow_register_visibility.py --op imm --delay mov6
make verify-overflow-register-visibility
```

[Complete evidence and diagnostic replay](../../results/2026-10-20-overflow-register-visibility/README.md).

The later [default activation guard](../../results/2026-10-20-overflow-guard/README.md)
now refuses unresolved unsynchronized overflow activation instead of silently
using the incomplete prediction. The old hypothesis remains explicitly opt-in;
all original counterexamples and historical manifests stay preserved. This
does not supply the missing physical activation/timing model.
