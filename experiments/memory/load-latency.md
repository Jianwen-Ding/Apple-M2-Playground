# Device-load latency by pointer chasing: G14C B1 — 2026-10-10

Direct DRM path (no Mesa). Each hop is `device_load r2 = table[r2]` (i32,
uniform base u8_u9, element-scaled register index) followed by `wait 0`. A loop
runs 16 hops per iteration (see [loops](../control-flow/loops-and-alu-timing.md)),
so each hop includes ~1/16 of the ~38-cycle loop overhead, about 2.4 cycles.
Tables are a single random cycle (Sattolo) over elements `stride` bytes apart;
other words are 0xffffffff. All 32 lanes of one SIMD group chase the same
chain. The oracle is the exact final index after K·M hops, computed on the host.
The emulator runs every chase against its real table before the GPU does.

`make verify-memory` checks every figure here against
[retained evidence](../../results/2026-10-10-agx-memory-latency/README.md):
40 variants, 13.2 million dependent loads, all exact.

## Latency curve (64 B stride, warm = median of last 8 of 30 submits)

| footprint | ns/hop | level (interpretation) |
| --- | --- | --- |
| 2–8 KiB | 36.0–37.8 | first level: ~50 cycles, scales with GPU clock (112 ns cold = 49.9 cycles at 444 MHz) |
| 12–64 KiB | 90.7–104.4 | second level: ~122–134 cycles, also GPU-clocked (fresh 32 KiB run: 276 → 167 → 126 → 97 ns) |
| 128 KiB | 121.6 | gradual second-level spill |
| 256 KiB | 154.0 | |
| 512 KiB | 221.4 | |
| 1–32 MiB | 348.6–351.7 | flat plateau; little clock dependence |
| 64 MiB | 369.7 | |
| 128 MiB | 378.5 | |
| 256 MiB | 387.9 | |

* **The first level holds between 8 and 12 KiB per core.** Latency more than
  doubles across that step (37.8 → 90.7 ns).
* **The second level spills gradually** from 64 KiB to ~1 MiB, possibly a
  set-associative or shared cache with random replacement. Its exact size is not
  determined.
* **Beyond ~1 MiB the latency is flat to 32 MiB, then rises slowly to 388 ns** at
  256 MiB. This could be the 1–32 MiB range being served by the SoC system-level
  cache with DRAM beyond it, or DRAM throughout with page effects. These runs do
  not distinguish the two; a bandwidth probe might.

## TLB versus cache (one line per 16 KiB page)

With `--stride 16384`, every element is on its own page, so the page count is
footprint/16 KiB while the cached data is only 64 B × elements.

| pages | lines touched | ns/hop | 64 B-stride value at the same line footprint |
| --- | --- | --- | --- |
| 16 | 1 KiB | 40.4 | ~36 |
| 64 | 4 KiB | 83–113 | ~37 (*see below*) |
| 1,024 | 64 KiB | 104.2 | 104.4 |
| 2,048 | 128 KiB | 121.5 | 121.6 |
| 16,384 | 1 MiB | 380.7 | 348.6 |

Latency follows the *line* footprint, so capacity dominates. Spanning 16,384
pages (256 MiB) adds about 32 ns at most. The 64-page anomaly (4 KiB of lines
missing the first level) fits limited first-level associativity for addresses
16 KiB apart. A first-level TLB limit near 64 entries is not excluded.

## Implications

* **First-level hits cost ~50 cycles; a dependent load chain is far slower than
  ALU work** (2 cycles per op). A CUDA backend must issue loads early and
  interleave independent work. This probe issues `wait 0` right after every load,
  so overlapping loads (wait groups) remain untested.
* **Keep per-core working sets ≤ 8 KiB for the fastest level.** Threadgroup memory
  is a separate path and remains to be measured.
* **Misses cost 350–390 ns**, ~500 cycles at the top clock. Achieving bandwidth
  will require many loads in flight across many SIMD groups.

## Not yet established

Bandwidth; latency with many SIMD groups and divergent addresses; threadgroup
memory; stores; `wait` groups (the `g` field) for overlapping loads; and the
cache level boundaries beyond the first.

## Reproduce

```sh
make agx-loop-test   # includes two small hardware chases
make verify-memory   # offline checks of every number above
make agx-memory      # full re-measurement (~4 min)
python3 -B scripts/run_drm_compute.py --kind chase --lengths 4096,1048576 --steps 16 --trips 1000
```
