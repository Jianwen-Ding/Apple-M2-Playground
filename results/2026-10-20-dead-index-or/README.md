# Dead index-bit contribution evidence

256 records: two alternating stop masks, four initial low-bit seeds, 32 new
targets. Each has exact wait controls before and after, 768 dispatches total,
zero faults. The initial complementary depth-0/depth-1 target cases were
inspected separately before extending the matrix.

Each record retains exact shaders, initialized input, complete readback,
source/harness hashes, current-model gates, firmware samples, hypotheses and
watchdog/kernel/memory/recovery diagnostics. Layout matches stopped-shuffle-
index: original depths, prefix, paired immediate/register gathers before and
after termination/index update, final markers, guards. The oracle requires
all register-index outputs to equal immediate selection using only living
lanes' new low index bits. Historical retained-bit/source hypotheses are
preserved unchanged. Run `make verify-dead-index-or` for reconstruction,
provenance and independent full-buffer checks. See the
[finding](../../novel-results/2026-10-20-dead-index-or/README.md).
