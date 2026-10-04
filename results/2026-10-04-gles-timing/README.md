# GLES timing evidence — 2026-10-04

See [the calibration report](../../experiments/timing/gles-timer-calibration.md).
Exact compute readback passed; loaded elapsed timers failed plausibility.
Timestamp pairs remain uncalibrated. Full runs intentionally return status 1.

- `final-run/`: raw per-case uint32 input/output/guards/seeds, exact expected
  results, shader and compiler logs, API stdout/stderr, commands/timeouts,
  raw uint64 query values, host brackets, availability/disjoint state,
  independent verification, package/library/header hashes, and captured source.
- `confirmation-summary.json`: first full run, independently confirming the
  failure class and exact readback. Its full raw files remain in scratch.
- `negative-node/`: wrong node rejection before shader creation or dispatch;
  subsequent timing cases stopped; final control also refused the wrong node.
- `timeout-control/`: a sleeping CPU child was killed at its 50 ms timeout,
  with partial output retained. No GPU timeout was induced.
- `selected-manifest.json`: SHA-256 of selected evidence. Per-run `manifest.json`
  hashes the original scratch inventory; the omitted executable can be rebuilt.

Scratch origins:
`/scratch/apple-m2-playground/gles-timing/20261004T202821.910289Z-4881` (final),
`20261004T202744.165539Z-4815` (confirmation), and
`20261004T202845.121621Z-5098` (negative node), under the same root.
Do not treat scratch as versioned source. Recorded build dependency paths refer
to files at capture time. Captured scripts contain a `suite_seconds` environment
field meaning the timing schedule's 60 s bound; canonical script metadata now
spells this `timing_schedule_seconds` and separately records the 12 s final
control bound. Execution logic is unchanged by that metadata clarification.

Raw uint64 JSON results need an integer-preserving reader (Python, for example).
JavaScript numeric parsing can silently round them. Zero slots in unused query
positions are placeholders, not asynchronous query observations. Binary buffers
are little-endian uint32. Timestamp pairs' delta is derived by signed integer
subtraction; elapsed query values are retained exactly as returned.
