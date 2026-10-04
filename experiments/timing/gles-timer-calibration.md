# Bounded GLES timer calibration on installed G14C B1 — 2026-10-04

**Observed API failure:** loaded `GL_TIME_ELAPSED_EXT` results are near
2^64 and incompatible with enclosing host brackets, despite exact compute
readback, available query results, zero GL errors, and zero disjoint flags.
Timestamp pairs returned progressing, plausible values but remain uncalibrated;
these observations support no instruction latency or physical-cycle claim.

The canonical source is `/save/workspace/apple-documentation-playground`.
Read the workspace/AGX Probe instructions, repository method, backend report,
and [counter reconnaissance](shader-counter-candidates.md) before implementation.
The backend report is an earlier capability snapshot; the user reports P2 now
has exact compute readback. This experiment independently verifies its own
workload. Only `tests/gles_time.c`, `scripts/run_gles_time.py`, this report, and
`results/2026-10-04-gles-timing/` are owned here. No shared files or vendor sources
were edited, agents spawned, commits made, or pushes attempted.

## Question and bounded method

Can advertised elapsed and timestamp-pair queries provide sensible timing for
known, checked compute dispatches? The inspected upstream/local source offset
mismatch predicts corrupt elapsed boundaries; that is a source hypothesis,
not a proven installed binary implementation or identified runtime root cause.

The standalone C test uses unchanged Mesa checkout EGL/GLES declarations and
loads installed runtime entry points through `libEGL.so.1`/`eglGetProcAddress`.
It verifies EGL's actual render node `/dev/dri/renderD128`, DRM driver `asahi`,
and renderer `Apple M2 Max (G14C B1)`. Observed context: surfaceless EGL 1.5,
GLES 3.2 Mesa 25.1.9, extension `GL_EXT_disjoint_timer_query`, and advertised
64-bit elapsed/timestamp counters. Identity and limits are driver responses.
Runtime library hashes, kernel, package inventory, build dependencies, commands,
shader/logs, errors, raw query results and buffer bytes are retained.

Each case uses a fresh process/context. Inputs are 64 independent uint seeds;
one dispatch launches two groups of 32 lanes. From a read-only seed SSBO, the
shader evaluates `x = x * 1664525u + 1013904223u` for a runtime uniform repeat
count of 0, 64 or 256, then stores x. Zero repeats still loads and stores.
Python independently generates seeds and modulo-2^32 expected results and
compares all 80 output-buffer words: 64 results and eight guards at each end.
It also compares the separate 16-word untouched buffer and all 64 seed words.
No CPU expected-output writes follow initialization. This confirms retained
input/output behavior, not a machine instruction count: shader binary inspection
was not performed and compiler transformations remain possible.

Schedule per run: initial no-dispatch control, empty elapsed, empty timestamp
pair, one zero-repeat warmup per loaded query type, then three samples per
query type at each of 0/64/256 repeats, and a final no-dispatch control.
That is 20 dispatches, at most 16,384 recurrence iterations per dispatch.
Warmups occur in fresh contexts and therefore do not establish a steady warm
context/cache state. There is no adaptive escalation or exhaustive benchmark.
Numerically corrupt results are retained as calibration failures; the fixed,
modest comparison completes when APIs, waits and readback succeed. The first
GL error, completion/availability timeout or readback failure stops subsequent
workloads; a separate bounded no-dispatch final control is still attempted.

Fence waits use 50 ms calls, at most 40 calls and a 2 s host deadline. Query
availability polling has a separate 2 s deadline and at most 4,000 polls with
1 ms sleeps; the 64-bit result getter is called only after availability. Explicit
flushes precede availability checks. Every child has a 12 s timeout, process-group
kill, and at most 2 s further output collection. The timing schedule has a 60 s
deadline; inventory (10 s), build (30 s), and final control (12 s) are separately
bounded. A blocked GL call or mapping is covered by the process timeout.

Before and after fields retain disjoint and synchronous GL timestamp state.
`timing.json` preserves unsigned 64-bit query values without floating conversion,
availability, polling counts, counter widths, and four CLOCK_MONOTONIC brackets:
before query recording, after fence completion, after query/state reads, and
after exact readback capture. Unused query slots in controls are zero placeholders,
not queried zero values. Python JSON integers retain full 64-bit precision; readers
using JavaScript must avoid rounding these raw integers through IEEE doubles.

## Hardware/API observations

Two full runs completed their exact output/guard/seed/control checks, including
final unchanged readback. Both found the same elapsed failure class. No API error,
completion timeout, disjoint flag, shader error or readback mismatch occurred.
Every used query was available on its first post-fence availability poll.

Final evidence run `20261004T202821.910289Z-4881`:

| Case | Raw query / pair delta, ns per API | Host bracket to fence, ms |
| --- | --- | --- |
| Empty elapsed | 1 | 0.053458 |
| Empty pair | raw [1986978600041, 1986978615416], delta 15,375 | 0.042417 |
| Loaded elapsed, 0 repeats | 18446742086639928075; 18446742086577248325; 18446742086515525450 | 1.268–1.625 |
| Loaded elapsed, 64 repeats | 18446742086453025408; 18446742086390804741; 18446742086325076116 | 1.245–1.656 |
| Loaded elapsed, 256 repeats | 18446742086279051658; 18446742086233808575; 18446742086183143741 | 1.254–1.288 |
| Loaded pairs, 0 repeats | 753,167; 768,125; 797,333 | 0.883–1.335 |
| Loaded pairs, 64 repeats | 774,125; 1,063,916; 784,167 | 1.238–1.557 |
| Loaded pairs, 256 repeats | 780,959; 786,167; 740,292 | 1.242–1.282 |

The complete pair endpoints are in per-case `timing.json` and `summary.json`;
pair deltas above are exact signed host subtraction, not modulo subtraction.
All ten loaded elapsed queries per run (including warmup) exceeded the enclosing
host bracket enormously. They resemble unsigned subtraction underflow. This
is an observed installed API failure, not observed AGX arithmetic behavior or a
measurement of a clock wrap. Empty elapsed returning 1 establishes neither
nanosecond resolution nor meaningful query overhead. Empty/control success
therefore does not validate loaded elapsed queries.

Pairs passed basic ordering and host-bracket plausibility checks. There is no
consistent increase from 0 to 64 to 256 repeats; three samples, fresh contexts,
possible lazy submission/compilation and concurrent agents cannot establish a
slope, resolution, command-boundary correctness or timing accuracy. The runner
labels these only `numerically_plausible`, never validated timers. Both full runs
exit 1 deliberately: `execution_verified=true`, `timers_usable=false`, and an
explicit calibration failure. API/process `failure=null` means no execution
failure; it does not indicate successful timer calibration.

## Source hypothesis and limits

[Counter reconnaissance](shader-counter-candidates.md) cites distinct compute
start/end fields consumed in batch cleanup but identical start/end destination
offsets in inspected Mesa 25.1.9 and local newer source. That hypothesis is
consistent with the huge loaded elapsed values, but this probe cannot identify
which timestamp destination firmware wrote or prove Fedora's binary matches
the inspected upstream source. No driver patch was attempted.

Its inspected constant-zero disjoint getter also means the observed zero flags
cannot independently establish clock stability or lack of resets/contention.
Synchronous state timestamp progression does not validate GPU completion-query
writes. Mesa batch/query placement, host-seeded timestamp queries and scheduling
can contribute to the plausible timestamp-pair values. No independent direct
UAPI start/end reference is available in this experiment.

Other agents may have run concurrently. Clocks and temperatures were not measured;
no isolated performance, ISA latency, shader special-register or physical-cycle
claim is made. These are GLES/compiler/driver/hardware pipeline observations
scoped to this installed stack and reported device revision.

## Reproduction, verification and failure evidence

```sh
python3 -B scripts/run_gles_time.py
```

Build uses `cc -std=c11 -Wall -Wextra -Werror -O2` with vendor headers read-only,
`-ldl`, and no GLES front library. Builds and Python syntax verification passed.
The negative oracle flipped one expected byte at output word 8 and rejected
exactly that mismatch without dispatching or mutating actual captured bytes.
A separate runner-process test timed out a sleeping child after 50 ms, retained
its flushed partial stdout, and returned after group kill. A wrong-render-node
run failed before compilation/dispatch; the schedule stopped at its initial
control and attempted its final control, which also rejected the mismatched node.
That negative test demonstrates stop-on-API/error behavior, not GPU recovery.
No real GPU timeout was induced.

[Selected evidence](../../results/2026-10-04-gles-timing/README.md) contains the
final run's raw outputs, logs, verification, hashes, and timeout/node negative
records, plus the first run's summary as independent confirmation. Scratch
binaries and bulk runs are regenerable under
`/scratch/apple-m2-playground/gles-timing/`; they are not canonical source.

Next: independently validate direct-UAPI compute timestamp destinations with
distinct initialized start/end words, then compare the same workloads against
that verified reference. Have the coordinator inspect exact Fedora build/patch
provenance and delegate any driver repair. Require boundary/reference validation
before promoting GLES timestamp pairs; shader timing-register provenance and
machine-code inspection remain separate tasks.

Independent review and correction verification: [compact record](../../results/2026-10-04-gles-timing/review.md).
