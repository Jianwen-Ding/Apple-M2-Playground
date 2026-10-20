# Masked r0 shuffle evidence

Twenty-four compressed records: incoming maximum depth 1..4, rotations 0/1,
three paths (original-state jump, known desired-state jump, return). Each has
exact payload-only controls before and after: 72 dispatches total, zero faults.

Each full table contains original/desired depth inputs, a prefix marker, two
snapshots of 32-source gathers through low r0 and initialized r10, a final
marker and 16 guard words. The table has 4,240 words; every writer/source pair
has a separate slot. The main output is also compared completely.

Exact shader/control bytes, initialized tables, full readbacks, firmware
samples, source/harness hashes, pre-submission model gates, diagnostics and
recovery metadata are preserved in each record. `make verify-masked-r0`
reconstructs exact programs and independently checks every word. The initial
three depth-3 cases were inspected individually before extending the matrix.

See the [finding](../../novel-results/2026-10-20-masked-r0/README.md).
