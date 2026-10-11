# Occupancy: up to 96 SIMD groups per core, register file 3,328 halves per lane slot, allocated in pairs

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Measured directly, not inferred from timing: each lane increments a per-core counter
(SR20-indexed device atomic with return), runs a long straight-line dependent chain, then
decrements. The largest pre-increment value on a core is its peak concurrency.

## Claim and scope

For workgroups of 128 or 256 lanes, over every declared register count from 16 to 248 halves
(step 8, two repeats, 60/60 exact):

```text
resident SIMD groups per core = min(96, 2 * floor(3328 / (2 * declared_halves)))
```

* **Hardware cap: 96 SIMD groups (3,072 threads) per core.** The preamble's slot 96 (see the
  [preshader finding](../2026-10-11-preshader-execution/README.md)) sits just past it.
* **Register budget: 3,328 16-bit halves per lane slot** (32 × 3,328 × 2 B = 208 KiB per core),
  allocated to **pairs** of SIMD groups, hence the even counts.
* No penalty up to 32 halves (r0–r15); 104 halves (52 32-bit registers) still allow 32 groups.

| Declared halves | 16–32 | 40 | 48 | 56 | 64 | 72 | 80 | 96 | 128 | 160 | 192 | 248 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SIMD groups / core | 96 | 82 | 68 | 58 | 52 | 46 | 40 | 34 | 26 | 20 | 16 | 12 |

Smaller workgroups cap lower whatever the register count: about 53–57 groups with 32-lane
workgroups and 84 with 64-lane workgroups (16 halves). At 48 halves and above, 64-lane groups
follow the formula.

A latency-bound loop over 2^20 lanes shows the cost: dispatch time is flat to 136 halves and
rises to 1.54× at 240–248 halves (`loop-timing-summary.txt`, 32-lane workgroups). A few
dispatches ran at about half time regardless of register count, which looks like a GPU clock
change; medians are used.

**Threadgroup memory (added 2026-10-11).** With 16 register halves and `--shared` declarations, resident
workgroups per core = **floor(65,536 / declared bytes)** (128-lane workgroups: 1 KiB → 96 groups (cap), 4 KiB → 16
workgroups, 12 KiB → 5, 24 KiB → 2, 32 KiB → 2, 48–64 KiB → 1; 256-lane: 8 KiB → 8, 16 KiB → 4, 21.5 KiB → 2).
A core has **64 KiB of threadgroup memory**, allocated per workgroup in 256-byte units, and the most
restrictive of registers, threadgroup memory and the 96-group cap sets occupancy. Reproduce with
`scripts/run_drm_occupancy.py --gprs 16 --shared 1024,4096,… --local-x 128` (`tg-sweep-lx128.json`, `tg-sweep-lx256.json`).

Not established: why 32/64-lane workgroups cap lower (workgroup slots per core or launch
rate), 256 declared halves (the launch field
wraps to 0 there and was not tested), and preamble register use.

## Reproducer and evidence

`make test-occupancy` (hardware), `make verify-occupancy` (offline, 0 failures).
Runner: `scripts/run_drm_occupancy.py`. [Evidence](../../results/2026-10-11-occupancy/README.md).

## Relationship to existing knowledge

SR19 reports the per-thread allocation (`max(8, roundup(nr_gprs, 8))`,
[SR finding](../2026-10-10-sr-resource-registers/README.md)). Mesa tracks register counts but
documents neither the register-file size, the pair granularity nor the 96-group cap.

## Compiler implications

* Use workgroups of at least 128 threads; 32-thread blocks cap at about 55 resident SIMD groups.
* Keep kernels at ≤ 32 halves (16 32-bit registers) for full occupancy, or trade registers for
  occupancy with the table above. CUDA's `__launch_bounds__`/`maxrregcount` maps to the
  declared halves; `cudaOccupancy*` APIs can use this formula.
* Counts are in 16-bit halves: 16-bit values genuinely halve register pressure.
