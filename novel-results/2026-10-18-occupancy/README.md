# Occupancy follow-ups: about 55 resident workgroups per core, shape-independent, and registers and threadgroup memory combine as a minimum

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. Same method as the
[occupancy finding](../2026-10-11-occupancy/README.md) (per-core counter incremented by a device atomic with return, a long straight-line
dependent chain, then decremented), with the peak now tracked on the device by an atomic *umax* of `old + 1` into a per-core slot so
any launch geometry works. Only Mesa-named atomic ops 0 / 1 / 6, no loops, 0 faults. Peak SIMD groups of a core = peak lanes / 32.

## 1. Why small workgroups cap lower: a workgroup-slot limit of about 55 per core, plus launch rate

* **At a fixed chain length the peak depends on the workgroup size** (2,000-step chain, 16 halves, 3 runs each): 32 lanes **46-48**
  groups, 64 lanes **81-86**, 96 lanes **93-96**, and **exactly 96 for every size from 128 to 1,024 lanes** (13 sizes).
* **The peak rises with the chain length, then plateaus** (250 / 1,000 / 4,000 / 16,000 steps): 32-lane workgroups 33, 36, **55**,
  **54**; 64-lane 36, 52, **94**, **90-94**; 96-lane 37, 65, **96**, **96**. So the short-chain numbers (and the 53-57 / 84 in the earlier
  finding) were bounded by how fast workgroups launch while earlier ones still run, not by a resource.
* **At saturation the limit is workgroups, not SIMD groups:** 32-lane workgroups (one group each) plateau at **54-55**; 64-lane ones
  reach 90-94 groups (45-47 workgroups, near the 96 cap); a workgroup of **8 threads** (one partly filled group) peaks at **53-56
  resident workgroups** (peak lanes / 8). Together: **about 55 resident workgroups per core**, regardless of how many lanes each has.
* For a CUDA runtime: `maxBlocksPerMultiprocessor` is about **55 on this device**, `maxThreadsPerMultiProcessor` 3,072 (96 x 32).

## 2. 2-D and 3-D workgroups: the thread count decides, not the shape

At the saturating chain (16,000 steps, 16 halves, 3 runs each), same-thread-count shapes agree:

| Threads | Shapes | Peak groups per core |
| --- | --- | --- |
| 64 | 64x1x1, 8x8x1, 4x4x4 | 89-93 |
| 128 | 128x1x1, 32x4x1, 16x8x1, 8x16x1, 4x32x1, 64x2x1, 8x4x4, 4x4x8, 16x4x2, 32x2x2 | **96** (all 30 runs) |
| 256 | 256x1x1, 64x4x1, 16x4x4 | **96** |
| 1,024 | 32x32x1 | **96** |
| 8 | 2x2x2 | 53-56 workgroups |

## 3. Registers and threadgroup memory together: the most restrictive limit wins

6 declared register counts (16, 48, 64, 96, 128, 192 halves) x 6 threadgroup sizes (0, 4, 8, 16, 24, 32 KiB), 128-lane workgroups,
2 runs, 16,000-step chain: **all 36 cells equal**

```text
resident SIMD groups per core = min(96, 2 * floor(3328 / (2 * halves)), 4 * floor(65536 / ceil256(shared bytes)))
```

(4 = SIMD groups per 128-lane workgroup; with no declared threadgroup memory the third term is absent.) The register term applies
per **pair of SIMD groups**, so a core can hold part of a workgroup (34 groups at 96 halves, 26 at 128 halves = 8.5 and 6.5 workgroups);
the threadgroup-memory term is per **whole workgroup** (floor(64 KiB / bytes) workgroups).

* **256 declared halves** was not run (the launch field wraps to 0; the result is unknown). The largest count tested earlier is 248.

Not established: the exact slot count (53-56 in the samples: it may be 54, 55 or 56), whether the slot limit also depends on the
barrier / atomic use of the kernel, and a threadgroup-memory model for non-128-lane workgroups beyond the whole-workgroup rule.

## Reproduce

`scripts/run_drm_occupancy2.py --mode sizes|steps|shapes|combined [--steps N]` (`offline` runs the program in the simulator),
`make verify-occupancy2` (offline, 9 checks against [results/2026-10-18-occupancy](../../results/2026-10-18-occupancy)).
