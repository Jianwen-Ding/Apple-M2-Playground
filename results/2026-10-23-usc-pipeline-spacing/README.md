# G14C USC pipeline spacing and queued launches (2026-10-23)

M2 Max, 64 GiB, Asahi Linux; ZLUDA `agx_runtime` stages each launch's USC
pipeline words in a shared 256 KiB ring. The previous 64-byte spacing needs a
USC cache invalidate after every launch. Without it, deep queues can execute
stale pipeline words and report `CUDA_ERROR_LAUNCH_FAILED` (B42).

## Probe

The phase-0 path of [B42's `b42_teardown.rs`](../2026-10-21-b42-context-teardown/b42_teardown.rs)
queues 200 vector-add launches, synchronizes once, and checks the result.
For this experiment, `agx_runtime` accepted `ZLUDA_AGX_USC_PIPELINE_ALIGN`
as the pipeline-word alignment, while `ZLUDA_AGX_USC_BARRIER=0` suppressed
the per-launch invalidate. Each run starts a new process and repeats that
phase. Faults below are CUDA 719 with missing firmware timestamps.

| Spacing | Result without per-launch invalidate |
| --- | --- |
| 64 bytes | Fault at command 17 in the first 200-launch queue |
| 128 bytes | Fault at command 59 in the first 200-launch queue |
| 256 bytes | 50 queues passed; fault at iteration 24 of a 500-queue run (command 112) |
| 512 bytes | 1,000 queues × 200 launches = 200,000 launches passed |

This establishes a working spacing on this G14C sample, not the physical USC
cache-line size. The ring wraps repeatedly during the 200,000-launch run, so
the test also covers reuse of ring addresses. The 512-byte spacing allows at
most 512 staged records per 256 KiB ring before it waits for older commands.

A 64-node vector-add graph replayed for 8,192 launches at 512-byte spacing
without per-launch invalidates produced the same three output hashes as the
barrier-on run (`47e085…`, `5ca1…`, `592d…`). Its mean GPU time fell from
4.832 to 1.708 µs per launch. The two runs used different iteration counts,
so this is an indicative latency measurement.

Geekbench 7 CUDA Preview completed all 11 GPU workloads with 512-byte spacing
and no per-launch invalidate. Its profile-based aggregate of per-kernel 10th
percentile times fell from 23.38 s with the invalidate to 22.30 s without it;
clock variation remains in this comparison. The Preview could not upload a
score because `browser.geekbench.com:443` was unreachable. These measurements
do not establish a Geekbench score or compare it with Metal.

ZLUDA now uses 512-byte spacing by default and invalidates after new code is
loaded. `ZLUDA_AGX_USC_BARRIER=1` restores Mesa-style per-launch invalidation
if another device shows stale pipeline words. No GPU hang occurred during the
probe; three deliberately unsafe spacings produced recoverable launch faults.
The rebuilt default driver also passed 100 more 200-launch queues with both
USC environment overrides unset.
