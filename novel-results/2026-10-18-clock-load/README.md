# The in-shader clock under load: one shared timer line costs 5 us at 1,024 lanes and 35-40 us at 65,536; per-core copies bring it to 0.6-2.7 us

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. Follow-up to the
[in-shader clock finding](../2026-10-11-in-shader-clock/README.md): the same CPU-written timer (low 32 bits of `CNTVCT_EL0`, 24 MHz,
41.7 ns per tick), now read by many lanes at once. Straight-line programs, no loops and nothing waits on a value; only
Mesa-emitted `device_barrier_1` (f59d) + coherent `device_load` + `wait 0`. The program was run in the Rust simulator first. 0 faults.

## Test

Every lane reads its timer copy 8 times in a row (each read = f59d, coherent load, `wait 0`) and stores the 8 words and its SR20 core.
`AGX_CPU_CLOCK_LINES = L` makes the CPU thread write L copies 128 B apart; lane's copy = `core & (L - 1)`, so L = 1 means every lane
reads the same cache line. Cost per read = (t7 - t0) / 7 ticks. Lane counts 1, 32, 1,024 (32 SIMD groups on 32 cores) and 65,536 (all 38
cores, many groups each) x L = 1, 2, 4, 8, 16. Two independent sweeps (one dispatch per cell, the last of 5 submissions).

## Results (median cost of one clock read, ns; the two sweeps agree within +-25%, one cell by 1.5x)

| Lanes | L = 1 | L = 2 | L = 4 | L = 8 | L = 16 |
| --- | --- | --- | --- | --- | --- |
| 1 | 970 / 821 | 768 / 839 | 845 / 821 | 804 / 792 | 798 / 792 |
| 32 (one SIMD group) | 839 / 756 | 839 / 839 | 839 / 804 | 839 / 804 | 851 / 690 |
| 1,024 | **5,077 / 4,893** | 1,815 / 2,750 | 1,089 / 815 | **571 / 560** | 827 / 726 |
| 65,536 | **40,298 / 34,393** | 21,565 / 18,768 | 4,024 / 4,173 | 2,661 / 1,905 | **2,250 / 2,702** |

* One lane, or all 32 lanes of one SIMD group, read in **0.7-1.0 us** (the older 0.4-0.75 us figure was a different loop shape).
* **Contention on a single line is the cost.** 32 cores reading one line cost 6x a single read; the whole GPU (65,536 lanes) 40x, with a
  p90 above 45 us. **One copy per core group removes it:** at 1,024 lanes 8 copies are as fast as one lane (0.56-0.57 us); at 65,536
  lanes 16 copies cost 2.3-2.7 us (15x less than one copy), still above the single-lane cost because several groups share a core.
* A `clock()` implementation should give each core (or each few cores) its own timer line; `%globaltimer` readers that all hit one
  line will serialise.
* **Correctness under load:** in all 40 cells every lane's eight reads were monotonic, no result word was missing, and all lanes of
  a SIMD group read identical values. The first reads of the 32 cores of a 1,024-lane dispatch with 8 copies differ by at most
  **0.12-0.2 us** (one tick is 0.04 us), which bounds the cross-core staleness plus launch skew of this timer to about 0.2 us when the
  line is not contended. With one shared line the spread was up to 4.7 us (queueing on the line, not a different clock). At 65,536 lanes
  the first-read spread (60-600 us) is the launch spread of the dispatch.

Not established: true cross-core skew separate from staleness (there is no common instant to compare against), the L2/SLC's own
contribution (the copies share the same CPU writes), `clock64()` beyond the low 32 bits (the CPU thread writes 32 bits), the cost of the
CPU thread itself, and the cost-model op: `cost::clock_read_ns(active_lanes, copies)` in the simulator now returns this table (means of the two sweeps, log-interpolated in lanes; `make verify-clock-model` checks the constants). The generic fence / load model predicts only about 0.34 us per read for the same instructions on GPU-resident data: the rest is the load fetching the CPU-written line.

## Reproduce

`scripts/run_drm_clock2.py offline|hardware`; `make verify-clock2` (offline, 10 checks against
[results/2026-10-18-clock-load](../../results/2026-10-18-clock-load)).
