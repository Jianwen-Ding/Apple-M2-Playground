# Zero-count synchronization evidence

34 compressed records matching the ordinary-r0-write matrix: register-source
mixed patterns through31 and all four forms with uniform 1/2/3/31 inputs.
Each has exact IF/wait controls **without pop0** before and after: 102
dispatches, zero faults. Exact code/input/readbacks, source/harness hashes,
write encodings, complete-model gates, synchronization/skip hypotheses,
firmware samples and diagnostic/recovery metadata are preserved unchanged.

The 176-word layout retains input, prefix, immediate post-write snapshot,
post-pop0 snapshot, final marker and guards. The first snapshot is full-group;
the second contains only zero-counter lanes. `make verify-r0-pop0` independently
checks every word and source hash, counts exactly one candidate pop0 and none
in controls, and replays original behavior offline. See the
[finding](../../novel-results/2026-10-20-r0-pop0/README.md).
