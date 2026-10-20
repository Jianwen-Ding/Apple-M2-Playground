# Shuffle from a stopped source returns the issuing lane's value

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**Nine variants / 27 dispatches with exact controls, zero faults.**

An immediate-index `simd_shuffle` selecting a stopped source lane returns the
issuing lane's own source value in this matrix. This differs from a **masked
but living** source, whose initialized register value remains readable, as
[measured separately](../2026-10-20-masked-r0/README.md). Stopped lanes stay
absent after five pops; this fallback prevents inferring their stored r0 bits.

Construct depths 0..M, gather each source's low r0 and payload, then STOP the
active depth-0 lanes. Pop once to activate depth-1 survivors and gather again.
Finally pop four more times and write a marker. The control replaces only the
2-byte STOP with wait and therefore keeps every lane alive. Both complete
programs pass their recorded simulator hypothesis before hardware submission.

The first depth-3 payload repeats original depth values; its stopped-source
reads give 1 rather than the expected 0. A unique lane-ID payload resolves the
substitution: every surviving writer reads **its own ID** for every stopped
source. Source addresses of still-living lanes, including masked depth-2/3/4
lanes, return the selected source's ID. The depth-1 case has multiple surviving
writers in each quad, further distinguishing individual self values.
Eight unique-payload cases cover maximum depths 1..4 and rotations 0/1; the
original repeating-payload case is retained as the ninth observation.

The counter gather also returns zero when selecting a stopped source, but
surviving issuing lanes have r0l=0 themselves. Thus that zero does **not** read
the stopped source's storage. The original attempt to test retained-zero dead
counter storage was inconclusive and its simulator mismatch is preserved.
The hypothesis that one fixed surviving source is substituted also fails when
writers have different IDs. No uninitialized data is read: all source payloads
and low counters were initialized within this same shader before termination.

Every complete main/table word matches the independent self-fallback oracle,
including final markers absent in stopped lanes, masked destinations, input
planes and guards. Both exact controls and all watchdog/kernel/memory recovery
diagnostics pass. No fault or hang occurred. Initial variants were inspected
individually before completing the rotated matrix.

Simulator d90cdcd still reads the original stopped source's register, giving
**nine retained counterexamples**. The original builder versions and failed
hypotheses are archived by hash. Register-index shuffles, other native shuffle
forms and later mask operations remain follow-ups before generalizing the
immediate-source fallback in the simulator. No timing inference is made.

```sh
python3 -B scripts/probe_stopped_r0.py --depth 3 --payload lane --hardware
make verify-stopped-r0
```

[Full evidence](../../results/2026-10-20-stopped-r0/README.md).

The later [shuffle-liveness simulator correction](../../results/2026-10-20-shuffle-liveness-model/README.md)
implements both measured rules in commit bf03118. Every original program here
now replays exactly. Initial hypotheses, diagnostics and source bytes remain
unchanged; current builders require the measured model before new submission.
