# Device atomics: one hot word serialises at 0.86 ns per lane-operation; 32 lanes are not combined

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, long-command clock
keeper. Simulator task safe-02 step 1.

## Claim and scope

**Test (`scripts/run_drm_atomic_contend.py`):**
- L lanes each run R = 64 device `atomic add` without return (the validated form) on word (gid mod K) × spacing.
- Two modes: every lane, or only lane 0 of each SIMD group.
- Two spacings: one address per 64 B line, or adjacent words.
- 40 configurations. Every table equalled (lanes per word) × R exactly, and each kernel first passed the simulator's
  `agx_run` with its table oracle.

| Pattern | Throughput |
|---|---|
| **one word**, 1,024-65,536 lanes (every lane, or one lane per group) | **0.84-0.96 ns per lane-operation** (~1.16 / ns, ~0.83 / cycle at 1,398 MHz) |
| distinct words, one per 64 B line, ≥ 32,768 lanes | 18-26 operations / ns GPU-wide |
| distinct words packed 16 per line (lanes 0-31 → 2 lines) | 111-156 operations / ns |

- **A hot word serialises every lane separately.** 32 lanes of one instruction on the same word cost 32× one lane.
  The hardware does not combine them, so a compiler should aggregate explicitly (subgroup reduction + one atomic).
- **Packed distinct words are 4-6× faster than one word per line.** This is consistent with per-line combining of
  an instruction's lanes.
- The `atomcontend` workload with 32 counters (2 lines, hashed lanes with collisions) is almost as slow as 1 counter
  (3,302 against 3,633 µs). Lanes that collide within an instruction appear to serialise per line. **Open:**
  modelled only for identical words.

## Simulator changes (`AGX-Performance-Simulator/rust/src/cost.rs`)

- **`atomic_same_word_rate` 2.0 → 0.89 per cycle.** The one-word microbenchmarks are now predicted within 6%
  (60.9 / 1,908 / 3,549 µs against 61.2 / 1,808 / 3,612 µs).
- **A dispatch now ends only when its device-atomic pipe has drained.** Before, a shader that ends right after
  no-return atomics (Mesa's code) finished before its serialised atomics:
  - the `atomcontend` probe went from 11.5 to 3,549 µs (measured 3,633) for one counter;
  - the workload total went from 57 to 4,882 µs (measured 7,492).
- No regressions: `verify-cost-model` identical, `verify-dispatch` and `verify-scaling` unchanged, `suite-check`
  721/721. `cellsort` / `hough` / `csrbuild` predictions moved toward their measurements (639 → 654, 239 → 286,
  386 → 421 µs; measured 2,077 / 687 / 754).

## Reproducer and evidence

- `make atomic-contention`: GPU, with the clock keeper.
- `make verify-atomic-contention`: offline, 6 checks.
- [Evidence](../../results/2026-10-16-atomic-contention/).

## Implications (CUDA)

- `atomicAdd` on a single global counter from many threads costs ~0.86 ns × the thread count, GPU-wide.
- Warp-aggregate (one atomic per warp after a subgroup reduction) for a 32× gain.
- Spreading counters over separate words in shared lines is cheaper than padding them to separate lines.
