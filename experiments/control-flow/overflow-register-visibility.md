# Overflow register visibility with prepared output indices

2026-10-20, before hardware. Earlier first-shuffle observations also change
address calculation when a following AND is removed. Do not infer an annulled
shuffle alone. Prepare every output index while all lanes issue, initialize
the tested destination to 0x1234 and all payloads to 0xbeef, record that seed,
then seed low-r0 and push across the boundary. Store the first operation's
destination directly with no address arithmetic or masking; store it again
after wait0 and finally in all lanes after a bounded unrolled drain.

Compare immediate, copy, add, AND and the five native shuffle first operations.
The cached mode leaves all lanes issuing before push; consistent mode uses
pop0/wait0 before push. Delay controls use wait0, pop0 or initialized scratch
mov instructions. Known controls use simple IF/wait0 without r0 writes or
the tested push, selecting the independently computed final zero membership.
Every complete candidate/control program first passes the simulator and a
full-buffer scalar oracle. All accesses use preinitialized allocated indices;
there is no branch, loop, barrier or uninitialized source. Values stay within
the proven unrolled pop3 drain, including the largest possible seeded count.

Start with low-depth control then high-boundary shuffle and immediate cases,
inspect all checkpoints and exact recovery, then select one discriminator at
a time. Save complete evidence before hardware; recovered faults may proceed
only after exact recovery. Blocked process/failed recovery prevents more GPU
submissions. Preserve mismatches rather than imposing the prior interpretation.

Outcome: 27 programs / 81 dispatches, exact controls, zero faults. Immediate,
copy and add can retain the seed in all overflow destinations; shuffle's
effect depends on lane in the tested layouts. Seven/eight intervening moves
make the immediate case exact; six makes only its lowest overflow destination
exact. Shuffle is exact from six tested moves; up to five remains affected.
All addresses were prepared before divergence and retained values persist
after wait/drain. This is broader than a shuffle-only rule, and not a cycle
calibration. [Report](../../novel-results/2026-10-20-overflow-register-visibility/README.md).
