# Differential special-register scan on the direct DRM path — 2026-10-11

`scripts/run_drm_sr_scan.py` reads all 256 `get_sr` selectors per lane in **one
dispatch**, through the [direct DRM path](../baseline/direct-drm-compute.md). Each
selector is stored to `table[s·S + lane]` over a sentinel table. The control's
own output oracle must pass, and inactive lanes' slots must stay untouched. Each
configuration changes one launch parameter through `drm_compute`'s `AGX_*`
overrides, which Vulkan never exposed. Raw records are up to 1.2 GB and stay in
scratch. `scripts/extract_sr_scan.py` keeps compact summaries in
[results/2026-10-11-sr-direct-drm](../../results/2026-10-11-sr-direct-drm/), which
`make verify-sr-direct` checks (14 checks).

112 scan dispatches ran across 21 retained sessions with no fault or timeout. One layout was
refused by the harness before submission, because the code and pipeline words
would have overlapped.

## New identifications

### SR32 = USC offset of the dispatch's pipeline words

| pipeline words at | code at | SR32 |
| --- | --- | --- |
| 0x1000 | 0x2000 | 0x1000 |
| 0x4000 | 0x2000 | 0x4000 |
| 0x8040 | 0x2000 | 0x8040 |
| 0x40 | 0x2000 | 0x40 |
| 0x3000 | 0x5000 | 0x3000 |
| 0x1000 | 0x5000 | 0x1000 |

SR32 is the CDM launch word 1 `Pipeline` field (USC-relative), readable inside
the shader. It explains the 2026-10-04 Vulkan observation (0xfff88000, falling by
0x24000 per command buffer): Honeykrisp allocates each command buffer's pipeline
words downward in its USC heap.

### SR17 = per-core hardware SIMD-group slot

* Uniform within every SIMD group in all 87 executed scans.
* In 45 of 46 light-load scans (1-D, 2-D and 3-D workgroups up to 1,024 threads)
  it equals SR53 (SIMD-group index within the threadgroup) lane for lane. That is
  why earlier scans mistook it for a copy, or saw zero.
* Under load the two separate. With 2,048 one-SIMD workgroups (~54 per core), SR53
  is 0 everywhere while SR17 takes 30–40 distinct values on every core (0–39).
  With 4-SIMD workgroups it spans 0–59.
* Its range shrinks with register allocation. In a resident sweep (an
  emulator-checked ~1 ms delay loop keeps groups alive), 1,024-thread groups reach
  64 values at ≤ 64 registers, 48 at 96, ~40 at 128, and 31–38 at 160–256.
  4-SIMD groups give 60/48/40/32/24 at 32–64/96/128/160–224/256 registers.
* The single light-load exception: one run gave workgroup 0 SR17 = 16 at 32 lanes.
  It was not reproducible (3 repeats), consistent with a slot allocator that
  usually but not always starts at 0.

This matches how NVIDIA implements PTX `%warpid` (a volatile hardware warp slot on
the SM), whereas SR53 is the stable index within the block. The distinct-slot
counts measure the slot ID space used over a whole dispatch, not peak
concurrency. An exact occupancy formula needs per-group timing, which no shader
clock provides yet.

### SR113 is random

Only ever 0 or 8, and identical configurations disagree (`order-shru`: 8, 0, 0, 8;
base, base-repeat and order-shru together: 3 of 18 runs gave 8). It is not tied to any parameter varied here.

## Inside the preshader (preamble)

A Preshader word points at a preamble that reads selectors with `get_sr` and
writes each to uniform halfs 32 and up with `uniform_store`. The main shader copies
those uniforms to the table and also stores its own SR20/17/0/24 beside them.
Uniform register count 5 × 64 halfs, preshader register count 16 halfs.
A constant-writing preamble first proves delivery: all 128 values arrive in every
lane.

| selector | preamble | main shader | reading |
| --- | --- | --- | --- |
| SR57, SR59 | 1, 1 | 4, 32 | the preamble runs with **one active lane** |
| SR0 | 0 | workgroup id | no workgroup context |
| SR17 | **96** on every core | 0–63 | a **dedicated SIMD-group slot** beyond the normal range |
| SR24 | **5** | 2 | first movement of this constant: a **program-kind code** (2 = compute main, 5 = compute preamble) |
| SR20 | equals the main shader's SR20 in **every lane** (66,112 lanes, 3 shapes) | | **uniforms written by a preamble are per core** |
| SR15, 25, 97, 114, 60, 63, 32, 19, 7 | same as main | | |
| 128–255 | all 0 | | including Mesa's helper SR144/146/147 |

**The preamble runs exactly once per core per dispatch, only on cores that receive
work.** A per-core counter incremented with a device `atomic add` reads 1 on every
core: 2 runs for 2 workgroups on 2 cores, and 38 for 512 or 2,048 workgroups
(12–60 per core). The atomic itself (new here, no return value) was validated
first: 33, 64 and 65,536 lanes each adding 1 to one word give exactly those
counts.



**The No preshader / Preshader word must be the last USC pipeline word.** Four
layouts violated it: Registers after it, Shader after it, fully reversed, and
Preshader first. All four executed nothing: ~5–6 µs, output and table untouched,
no error and no fault. Layouts keeping it last in other orders (`shrun`, `rhsun`)
executed normally. A real Preshader word (tag 0x38, Mesa's 0xc08000) pointing at a
one-instruction `stop` preamble also works and changes no selector.

## Parameters that change nothing

Helper-program data (0x1122334455667788) and cfg (binary 0), low queue priority,
a 4-entry sampler heap, and the launch word-0 uniform, texture and preshader
register counts changed no selector beyond the known varying SR21 (context) and
SR113 (random). SR144/146/147 (Mesa: helper op/args) stay 0 in the main shader,
even with helper data set.

## Updated tally (compute stage)

| Category | Count | Registers |
| --- | --- | --- |
| Identified | **30** | previous 28 + **SR17** (hardware SIMD-group slot) + **SR32** (pipeline-word offset) |
| Nonzero, unexplained | 6 | SR15 = 16, SR25 = 2, SR97 = 2048, SR114 = 136 (constant in main and preamble); SR60 = 15; SR63 (Mesa: is_active_thread, untested) |
| Behaviour known, meaning partial | 2 | SR24 (program kind: 2 main compute, 5 preamble); SR113 (random 0/8) |
| Mesa-named, not testable from compute | 6 | SR14, 62, 124, 144, 146, 147 |
| Always zero | 212 | — |

## Reproduce

```sh
make sr-direct          # base, single-parameter, preshader and atomic configurations (~6 min)
make verify-sr-direct   # offline checks of every claim above
python3 -B scripts/run_drm_sr_scan.py --configs base,occupancy-2048wg
```
