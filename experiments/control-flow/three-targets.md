# Three target addresses under scattered call/return participation

Question before hardware, 2026-10-20: do lowest-active selection, call partition
masking, call-link writes and return reconvergence hold when all three distinct
callee addresses are present in active lanes? Existing matrices used two.

Use one 32-lane group, source r30, three decoded in-program A/B/C landing blocks,
no loop/barrier, and a bounded fallback. Seed inactive holes; force first lane,
first+2 and lane 31 active and assign all three addresses among them. Mask lower
lanes and first+1. Rotate the first lane's target through A/B/C to exclude an
address preference. Every input/ID/trace address is initialized before masking.

For calls, trace matching callee entrants and their links before pop, the
post-pop marker and r1 on all lanes. For returns, trace inactive lanes after
pop 1, all lanes after pop 2, and preserved r1. The exact full program must match
an independent scalar oracle in the current measured simulator. Also gate each
of three uniform-operand and three direct-jump replacements; verify every
destination is an instruction boundary. Known-op jump-A hardware controls
bracket the variant; retain full readback/guards and watchdog diagnostics.

Start kind call then ret at k=1, winner C, seed 103. If exact, extend to k in
0,1,5,8,16,24, winner A/B/C and seeds 103/809 for both kinds. Stop the batch on
any unexpected semantic result or fault, analyze saved diagnostics, and require
exact recovery before further GPU work. Failed recovery or a blocked process
ends submissions. `probe_three_targets.py --kind call|ret [--hardware]`.
