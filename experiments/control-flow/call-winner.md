# Indirect call winner with masked physical lane 0

Question before hardware, 2026-10-20: after the return winner matrix, does
`call r30` likewise select the lowest active lane's operand when active
operands disagree and lane 0 is inactive? Does it mask nonmatching active
lanes and write links only in the entering partition, as measured when lane
0 is active?

No return is used. Both targets are decoded in-program callees. Each records
entry identity and r1 before popping the mask once, records a post-pop marker
and stops. A bounded fallthrough path also records its own marker and stops.
All IDs, addresses, targets and output slots are initialized before masking.

For a suffix beginning at k, lane k alone holds B and all others hold A, then
swap. The lowest-active hypothesis predicts entry only in lane k, with the
buffer-relative two-byte call link; stale-lane-0 selection predicts A with
entry in the other active lanes. Record the complete trace rather than assume
that either model must be correct.

First run k=0 as the established lane-0-active baseline, then k=1. For each
candidate, simulate both filtered uniform-call substitutions and forced jump
landings with a synthetic link. For an empty matching set, separately simulate
empty-call fallthrough and a forced empty-mask landing. The actual divergent
model rejection is retained; surrogate gates do not validate unknown selection.

Use `probe_call_winner.py --first K --winner A|B [--hardware]` and the shared
unsafe watchdog. Exact known-op controls bracket each candidate. Preserve all
fault, mapping, kernel, memory and recovery diagnostics; stop GPU submissions
on failed recovery or a blocked host process. Never rerun a fault blindly.
