# `wait` costs ~5 units even when nothing is pending, ~11 in loop bodies larger than 512 bytes

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, one SIMD group, no memory
instructions in flight. Reference units (× 1.049 = real cycles).

## Claim and scope

k idle `wait` instructions per repetition, 8 repetitions per loop trip (`waits.json`), slot 0 or 1:

| k | 1–30 | 31 | 32 | 40 |
| --- | --- | --- | --- | --- |
| units per wait | 4.7–4.9 | 10.9–11.3 | 10.8–11.2 | 10.9–11.0 |

* An idle `wait` is not free: about **4.9 units (5.1 cycles)**, the same for slots 0 and 1.
* The cost more than doubles exactly when the loop body grows past **512 bytes** (31 two-byte waits × 8 +
  18 bytes of loop control = 514 B). Bodies of independent 8-byte `iadd`s up to 2 KiB show no such step
  (`fetch-body-size.json`), so the effect is specific to `wait`; a plausible reading is that `wait`
  restarts instruction fetch, which is cheap from a ~512-byte loop buffer and costlier otherwise.

Not established: straight-line (non-loop) code (the cost model assumes the large-body cost), waits with
pending work, other synchronisation instructions, and whether the 512-byte boundary is alignment-dependent.

## Reproducer and evidence

`python3 scripts/cost_probes.py waits`; `results/2026-10-11-cost-model/waits.json`. Modelled in
`scripts/agx_cost.py` (`mark_loops`, `wait_idle`, `wait_idle_big`).

## Compiler implications

* Do not emit `wait` defensively: each costs ~5 cycles even with nothing to wait for (Mesa's
  `AGX_MESA_DEBUG=wait` mode would be expensive).
* Keep hot loops that contain waits under 512 bytes of code.
