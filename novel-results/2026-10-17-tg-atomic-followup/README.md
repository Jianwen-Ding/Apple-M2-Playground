# Threadgroup atomic opcode and control-bit follow-up

27 variants, each bracketed by exact hardware controls and preceded by a
complete-program simulator check against an independent integer oracle.
All completed on M2 Max G14C, with no new faults or hangs. The boot's recovered
event count stayed **3/30**. No timing claim is made.

| Encoding change | Cases | Observed result |
| --- | ---: | --- |
| Opcode 11–15, full mask | 5 | Only the pre-instruction marker was stored |
| Opcode 11–15, odd lanes active | 5 | Same; even lanes did not resume after `pop_exec 3` |
| Opcode 11–15, empty mask, instruction issued | 5 | Same, despite no active lanes |
| Opcode 11, empty mask, `jmp_exec_none` skips it | 1 | Continuation and harness stores completed |
| Sub: clear bit 36 or 47 | 2 | Exact integer-sub baseline, including all shared memory |
| CAS: clear bit 36 or 47, or set bit 40 | 3 | Exact CAS baseline, including matching/nonmatching compares |
| Sub/CAS: clear bit 34 | 2 | Baseline; register offset r0l is zero in these full-mask cases |
| Sub/CAS: set bits 45+46 together | 2 | Exact integer baseline |
| Sub/CAS: clear bits 36+47 together | 2 | Exact integer baseline |

The opcode results support **termination of the issuing SIMD group, including
inactive lanes**, rather than ordinary per-lane predication. This is measured
with one group only. Other groups' progress, shared-memory effects before
termination, different operand/control fields, and ordering effects remain
unmeasured. In particular, no shared-memory dump runs after an ending opcode;
an unchanged global table does **not** prove unchanged shared memory.

No float shared-memory add or 64-bit shared atomic was found. Bit 34 is already
decoded as the immediate/register offset selector; its result here is limited
to equal zero offsets. Bit 15 selects instruction length: clearing it makes a
six-byte instruction. The gate caught that change offline, and those proposed
bit-15 variants were **not submitted**. They need a separately constructed
short-form program, not a ten-byte instruction with stray trailing bytes.

The base instruction is `19952c01548000000c00` (sub) or
`19952c03548000000c00` (CAS), returning to r5, with r22l as shared address and
r6 (plus r7 for CAS) as source. Inputs include integers and float bit patterns.
Each lane accesses its own initialized word. Before the unknown instruction,
the program fills all 2 KiB of shared memory, initializes the first 32 words,
and synchronizes. There is **no barrier after the unknown instruction**.

Global table words 192–223 hold the before marker; 224–255 hold the immediate
continuation marker; 768–799 hold the marker after `pop_exec r0l, 3`.
Words 256–767 receive all 512 shared words if execution continues. Every table
and output word, including guards and untouched slots, is checked.

Run `make verify-tg-atomic-followup` offline. It reconstructs all 27 programs,
simulates all complete known-operation controls, checks every retained hardware
word and recovery control, and replays the 12 understood variants exactly.
The simulator explicitly rejects the 15 ending-opcode cases, including empty
masks: their shared-memory effects are not modeled. Previously an empty mask
silently skipped such an unsupported operation, contradicting these records.

Evidence: [results](../../results/2026-10-17-tg-atomic-followup/).
Reproducer: `python3 -B scripts/probe_tg_atomic_followup.py CASE` checks the
surrogate offline; `--hardware` submits one case with before/after controls.
Existing records cannot be overwritten. A recovered fault is logged; failure
of the recovery control stops further submissions.

For future hangs, the runner now saves the exact program and input before
submission, plus phase, kernel-log delta, firmware timestamps, available
readback, cgroup memory/pressure/events and `/proc/meminfo`. A host timeout also
captures this probe's process status, wait channel and mappings. Both dispatch
wait and post-kill pipe drain are bounded; a process still blocked after kill
prevents further GPU submissions. Partial JSON/readback is preserved.
See the [unified-memory follow-up procedure](../../notes/hang-memory-followup.md).
Six host watchdog tests pass, and three known-good hardware dispatches through
the updated watchdog matched the complete oracle with no fault.
