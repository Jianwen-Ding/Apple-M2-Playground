# First shuffle retains its destination after counter overflow reactivation

M2 Max G14C B1, direct DRM compute, 2026-10-20, recorded AC-online 0.
**27 programs / 81 dispatches** including the three base overflow cases.
Every dispatch completed, all independent pre/post controls pass, zero faults
or hangs. These are functional traces, not calibrated timing measurements.

A masked living lane holding 0xffff becomes counter zero after push1 and
participates in later stores. Its first immediately following native shuffle
leaves the destination's prior value visible, instead of the predicted source
value. The original record and exact-byte repeat both store 0x40 at word 2188,
with every other word exact. Initializing the destination before divergence
to 0x1234 or 0x5678 makes that first bad result equal the chosen seed. The
unseeded 0x40 is an observed value, not an architectural constant or inferred
initialization rule.

| Tested variation | First newly reactivated shuffle result |
| --- | --- |
| Immediate shuffle after push1, push2, push3 | Prior destination retained |
| All five native shuffle forms, zero relative offset for the four variants | Prior destination retained |
| Half-register shuffle or initialized ordinary payload source | Prior destination retained |
| Integer true IF in place of float true IF/push | Prior destination retained |
| One harmless mov_imm between push and shuffle | Prior destination retained |
| One wait0 between push and shuffle, for each n=1/2/3 | Complete buffer exact |
| Explicit pop0 between push and shuffle | Complete buffer exact |
| Duplicate the first shuffle, n1 | Second shuffle produces the expected value |
| Lane already issue-active before push, n1 | Complete buffer exact |

Push2 and push3 move the affected lane to the original 0xfffe and 0xfffd
sources, respectively; only their first post-push destination word differs.
A one-lane input rotation moves the failure with the newly reactivated lane
and changes the expected source-0 value to 60382, while the observed unseeded
destination is still 0x40. Later pop0/pop1 counter and payload snapshots and
the bounded final drain match in every case. Counter arithmetic therefore
matches the modulo-65536 hypothesis at these sampled checkpoints, but an
immediate shuffle has a separate execution-state effect.

This narrows the effect to shuffle execution around overflow reactivation;
it does not yet establish a general pipeline model, required cycle count,
behavior of newly masked destinations, or every intervening instruction.
One intervening ALU instruction failing while a second shuffle succeeds is
reason to avoid modelling this as a generic one-instruction delay. The tested
wait0/pop0 sequences are complete-program workarounds in this scope.

Every actual program first passes the current simulator's explicitly retained
increment/synchronization hypothesis. Independent controls read initialized
expected payload vectors under simple IF masks, without wide r0 writes or
the tested push. All memory access stays inside initialized tables; there is
no branch, loop, barrier, invalid target or uninitialized index. The largest
shader is below the harness limit and uses the already measured unrolled
pop3 drain. Exact source versions, complete readbacks, timestamps, watchdog,
kernel, memory, power, boot and recovery metadata remain in the records.

**Simulator c7e50f7 has 18 retained counterexamples** across this family:
the original high-boundary case and 17 diagnostics. Nine other complete
programs match. `make verify-overflow-first-shuffle` independently verifies
all buffers and explicitly requires the known mismatches rather than calling
them model passes. Its diagnostic manifest binds binary/source and record
hashes. The earlier 2,403-program exact corpus is unchanged and separate.

Further isolation: wait0 **after** the first shuffle does not fix its retained
readback; pop0 at that position does. Replacing the following AND with a
half-to-full move still fails. Removing the AND while using a fully defined
payload source changes the result further: the intended word 2188 is untouched
and table word 76 receives 0x40, consistent with the preinitialized index left
from an earlier load. Both addresses are inside the owned table. This is not
an out-of-bounds access, fault or hang. It also means the initial readback
cannot yet be attributed solely to an annulled shuffle destination write.
Register visibility, execution updates and intervening address calculations
need separation. The original observations/classifications remain intact.

Next discriminators should use output indices prepared before divergence and
directly read masked destination registers after
the first shuffle and distinguish which operation updates its execution mask.
Broader overflow matrices remain pending. [Evidence](../../results/2026-10-20-overflow-first-shuffle/README.md).

The [prepared-index follow-up](../2026-10-20-overflow-register-visibility/README.md)
extends destination retention to immediate/copy/add and records spacing/lane
dependence. A later [default model guard](../../results/2026-10-20-overflow-guard/README.md)
rejects unresolved activation until measured wait0/pop0 settlement; the known-
incomplete old hypothesis is available only by explicit opt-in. Original data
and failed predictions remain unchanged.
