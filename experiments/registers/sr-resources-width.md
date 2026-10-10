# SR18/SR19 resource registers and get_sr destination widths (G14C B1)

Second follow-up of 2026-10-10, after the [geometry/core-id report](sr-geometry-core-alt.md).
Same device and pinned driver (Mesa 25.3.6 honeykrisp, Apple M2 Max G14C B1).

**Results (hardware, compute stage):**

| SR | Shader-visible value | Driven by |
| --- | --- | --- |
| **18** | threadgroup-memory bytes rounded up to 256; 0 when none | exported `local_size` → USC Shared "bytes per threadgroup" |
| **19** | `max(8, roundup(nr_gprs, 8))`: per-thread register allocation in 16-bit registers | exported `nr_gprs` → USC Registers "register count" |

* PTX use: SR18 can supply `%total_smem_size` (with no dynamic shared memory, also
  `%dynamic_smem_size` = 0). SR19 is useful for occupancy diagnostics.
* No other selector (SR21 per-device state and intermittent SR113 excluded) changed
  with shared memory, push/uniform count, texture/sampler state count, scratch,
  preamble scratch, register count or preamble register count. **SR15=16,
  SR24=SR25=2, SR97=2048 and SR114=136 are not tied to any of those shader
  resources.** They remain unexplained hardware or configuration constants.
* **`get_sr` is 32-bit only.** A 64-bit destination encoding (D odd, `r2:r3`) never
  wrote r3 for any of 256 selectors, and r2 received the normal 32-bit value. A 16-bit
  destination (`r2l`) receives exactly the low 16 bits of the standard read, with
  the high half preserved, for 255/256 selectors (SR21 differs only by device). Together
  with the earlier paired-read sweep, no width of this instruction exposes a clock.

## Reproduce

```sh
make sr-shared            # SPIR-V shared arrays: 0..8192 words (all 256 SRs) + odd sizes
make sr-meta              # metadata sweeps + 7 single-field edits x 256 SRs (2082 runs)
make sr-width             # 64-bit and 16-bit get_sr destinations, all 256 SRs
make verify-sr-resources  # offline, with failure injection
```

## What Mesa provides and what the hardware provides

Mesa compiles a tiny shader and exports its binary. That is the delivery path.
Its source names the driver fields: `agx_shader_info` layout, and the USC Shared
and USC Registers control words with their 256-byte and 8-register granules. Mesa
does **not** say what any shader-visible special register returns. SR18 and SR19 have
no name in Mesa or applegpu. Every value here comes from GPU readback of edited
binaries. The struct layout was used only to find the knobs: offsets 0x82d push_count,
0x82f local_size, 0x835/0x839 scratch, 0x85f/0x860 texture/sampler counts, 0x861
nr_gprs, 0x863 nr_preamble_gprs. Each offset was confirmed against the export's known
values before editing (`run_agx_sr_meta.py` fails closed if they differ).

## Method

### Shared memory through SPIR-V (`run_agx_sr_shape.py --shared-words`)

The shape shader optionally routes its value through a `uint[N]` Workgroup array:
`s[lii] = value; OpControlBarrier(Workgroup, Workgroup, AcquireRelease|WorkgroupMemory);
data[...] = s[lii]`. The patched `get_sr` value therefore travels through threadgroup memory.
That path has a consequence: with the allocation set to 0, the shader reads back 0
whatever the SR (see "Pitfalls").

* All 256 selectors, sizes 0/32/64/…/8192 words: only SR18 and SR19 differed from
  the no-shared shader. SR18 = 256, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768.
  SR19 went from 8 to 16 because the shared shader compiled to nr_gprs 10 rather than 6.
* Odd sizes 132, 252, 260, 400, 516, 4000, 16388, 32000 bytes → SR18 256, 256, 512,
  512, 768, 4096, 16640, 32000: a 256-byte granule.

### Single-field metadata edits (`run_agx_sr_meta.py`)

Export the no-shared 32×1×1 shader, patch `get_sr`, edit exactly one
`agx_shader_info` field, refresh the wrapper SHA1, and run 3 groups (96 lanes).
Code bytes are identical across edits. Guards and the patterned tail are checked
on every readback.

* `local_size` 0, 256, 512, 1024, 4096, 16640, 32000, 65280 → SR18 the same
  value. This happens without any shared-memory instruction in the shader, so SR18
  reads the programmed allocation, not observed usage.
* `nr_gprs` 1, 2, 4, 6, 8 → SR19 8; 9, 12, 16 → 16; 20, 24 → 24; 32, 48, 64, 128 → same;
  100 → 104; 255 → 256.
* `nr_preamble_gprs` 0, 8, 16, 32 → SR19 stays 8.
* Full 256-selector scans for push_count=60, texture_state_count=4,
  sampler_state_count=2, scratch_size=1024, preamble_scratch_size=1024,
  nr_gprs=64, local_size=4096. Only SR19 (→64) and SR18 (→4096) moved.

### Destination width (`run_agx_sr_scan.py --preload … --width 16|64`)

* 64: `mov_imm r3, ~P; mov_imm r2, P; get_sr (Dt=2, D=5); wait; iadd r2, r3, 0`,
  with nr_gprs raised to 16 (via `patch_body(gprs=)`) so r3 is allocated. A
  control without the read must return ~P. Every selector returned ~P.
* Ad hoc check (not retained) of D=5 with each Dt for SR80/4/32: Dt=2/3 wrote the
  ordinary 32-bit value to r2. Dt=0/1 wrote the low 16 bits into **r2h**, so the D
  low bit selects the high half in 16-bit mode. Dt bit 0 (cache hint) changed nothing.
* 16: `mov_imm r2, P; get_sr r2l; wait`. Each lane equals
  `(P & 0xffff0000) | (standard & 0xffff)`, compared with the retained standard-read
  run from the previous report.

## Pitfalls and negative results

* Shader + shared allocation 0: the driver programs "no shared memory", and threadgroup
  stores/loads then silently return 0 rather than faulting. An early ad hoc run
  mis-read this as "SR19 = 0". Any probe that routes data through shared memory must
  keep the allocation nonzero.
* Editing `main_offset` (0x849) made the shader stop writing output (sentinels
  intact, no fault). The field is structural and is not a knob.
* SR113 alternated between 0 and 8 across otherwise identical edits. This matches
  the intermittent behavior in the original scan, so it is excluded rather than
  attributed to any field.

## Limits

One device, one driver build, compute only. "Programmed" values are inferred from
which exported field moves the SR. The final USC words were not dumped. SR18/19 were
not tested in other stages. The meaning of the SR15/24/25/97/114 constants remains
open; plausible next variables are stage type, core/cluster configuration, or a
different GPU generation.
