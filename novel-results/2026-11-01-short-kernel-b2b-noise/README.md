# Back-to-back medians of ~7 us kernels need thousands of commands: 300 leave them +-40% apart between runs

Status: confirmed on one device (M2 Max G14C), `agx_run_hw --back-to-back N` on ZLUDA captures, 2026-11-01.

## Claim

The same capture of a ~7 us kernel (results/2026-11-01-tg-reduction-tail/oneshot.ptx, 448 workgroups) gave b2b
medians of 7.5, 9.8 and 12.2 us in three runs of `--back-to-back 300`, and 7.0, 6.4, 6.4 us with `--back-to-back
3000`. A 16-28 us variant swung 16.5-27.8 us at 300 and 16.2-17.3 at 3000. Kernels of 50 us and more (the
shuffle-tree `_tg` probes, 70-270 us) agree run to run at 300.

## Implications

- The GPU clock ramps over the burst; 300 commands of a few microseconds are ~2 ms of work, too short to reach and
  hold the top state. Use >= 3000 (or >= ~20 ms of work) before taking a median of short kernels.
- Short-kernel comparisons with the AGX Performance Simulator taken at 300 carry this uncertainty (some 2026-11-01
  probe points around 10 us: tree1 at 38 workgroups, chase); the conclusions drawn from them rest on longer runs.

## Reproducer and evidence

[hardware.txt](../../results/2026-11-01-tg-reduction-tail/hardware.txt) (oneshot rows);
`/scratch/perf-goal/sim/hwone.sh CAPTURE --back-to-back N` (agx_run_hw with the capture's launch).
