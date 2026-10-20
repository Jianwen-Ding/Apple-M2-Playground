# Stale-issuing-mask RET evidence

34 records: three register-source forms with mixed maxima 1/3/31 and both
rotations; all four write forms with uniform 1/2/3/31. Each has exact known
IF/jump controls without RET/r0 writes before/after: 102 dispatches, zero
faults. Exact programs/inputs/readbacks, source/harness hashes, old-model
hypotheses, boundaries, firmware samples and diagnostic/recovery metadata
are preserved unchanged. The first record's all-false hypothesis assessment
predates the explanatory rule and remains unchanged; its original source is
archived by hash in source-before-model/.

The 240-word table contains input depths, prefix, target snapshots before pop
and after pops1/2/3, final/fallthrough marker and guards. Actual ordinary writes
leave all physical lanes active before RET; controls construct known depth2.
Uniform initialized r30 targets are valid in-program boundaries. A bounded
drain follows all observations. `make verify-ret-stale-exec` reconstructs
bytes, resolves original sources and independently checks every word plus
all 34 current simulator counterexamples. See the
[finding](../../novel-results/2026-10-20-ret-stale-exec/README.md).
