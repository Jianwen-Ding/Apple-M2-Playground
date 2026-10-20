# Scattered-mask call/return target selection and link scope

Question before hardware, 2026-10-20: do the suffix-mask winner and global
call-link observations survive holes among active lanes? Test every lowest
active position 1..31, both target assignments and two fixed random seeds.
Keep the program bytes unchanged; change only initialized active-bit inputs.
Force the first lane active, all lower lanes inactive, lane 31 active when
possible, and at least one hole above the first when possible. For positions
30/31 the physical range permits no interior hole; these remain edge controls.

Return hypothesis: the lowest active operand chooses the landing; previously
inactive lanes (including holes) reactivate at pop 1, all at pop 2. Call
hypothesis: only matching active lanes enter the chosen callee, one pop
reactivates everyone, and r1 changes in every issue-active lane while inactive
holes retain their initialized sentinel.

For every exact sparse table, rerun both uniform and forced-jump surrogate
oracles, retaining the actual simulator's unsupported diagnostic separately.
Do not reuse a prefix-mask gate as evidence for a new input table. Keep all
addresses inside decoded landing blocks, with no loops/barriers. The shared
bounded unsafe harness records controls, guards, kernel/firmware/memory state
and recovery; stop submissions if recovery fails or the host process blocks.
Runner: `probe_sparse_control.py --kind ret|call --first K --winner A|B --seed S`;
`--hardware` adds the bracketed hardware variant. Existing records are not
overwritten.
