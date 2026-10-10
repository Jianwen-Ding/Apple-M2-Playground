# SR geometry, core identity, and the bit-15 get_sr form (G14C B1)

Follow-up to the [256-selector scan](special-register-scan.md), run on
2026-10-10 on the same driver-reported Apple M2 Max (G14C B1), Mesa 25.3.6
honeykrisp, pinned driver SHA256 `26abaa59…1c65`. Three questions:

1. Which SRs carry workgroup geometry when local size and dispatch are 2-D/3-D?
2. Is SR20 (`core_id` in Mesa) a usable PTX `%smid`?
3. What does the `get_sr` encoding with bit 15 set (applegpu `TODO.sr_thing`) do?

**Answers (hardware, scoped below):** the Mesa/applegpu geometry names hold
across nine shapes. **SR7 = ceil(threads per threadgroup / 32)**, the number of
SIMD groups per threadgroup; no existing label covers it. **SR20 = `(cluster << 4) | core`**,
and its value set exactly matches the driver's enabled-core masks. The **bit-15 form
writes nothing observable**: it leaves its destination register unchanged for all
256 selectors and does not alter a following standard read.

## Reproduce

```sh
make sr-shape        # nine local/group shapes, 29 selectors, two samples each
make sr-core         # 2048 workgroups (65536 lanes), 20 selectors, three samples
make sr-alt          # bit-15 form, r2 preloaded 0xdeadbeef, all 256 selectors
make sr-alt-reread   # bit-15 form then standard read of the same SR, all 256
make sr-std-preload  # standard read with the same preload body: comparison baseline
make verify-sr-shape # offline: retained evidence + failure-injection self-test
```

Hardware targets write to `$(SCRATCH_ROOT)` subfolders. In this session `/scratch` was
root-owned and read-only for the probe user, so runs used `--output` under the
session scratchpad. Retained compact evidence: [results](../../results/2026-10-10-sr-shape-core/README.md).

## Method

### Shape probe (`scripts/run_agx_sr_shape.py`)

No GLSL compiler is installed, so the script hand-encodes SPIR-V 1.3 from the
Mesa grammar and validates it with the system SPIRV-Tools library. Each shader stores
`0x12345678` at `data[8 + linear]`, with

```text
linear = LocalInvocationIndex + L * (wg.x + nx * (wg.y + ny * wg.z)),   L = lx*ly*lz
```

so every lane has one known output slot. The C child (`tests/vulkan_compute.c`)
now optionally takes three group counts (default unchanged: `rounded/32,1,1`).
For each shape, Mesa's exported binary must first reproduce the exact constant on
export and on import. The patcher then finds the **unique** 6-byte 32-bit
`mov_imm rN, 0x12345678` and replaces it with `get_sr rN, SR; wait 0`. It
re-derives the destination from the decoded `mov_imm` and refreshes the wrapper SHA1.
Guards, padding and the patterned tail are checked on every readback.

Shapes (local; groups): 32×1×1;3×1×1 · 8×4×1;2×3×1 · 4×2×4;2×2×2 ·
16×1×1;2×1×3 · 64×1×1;2×1×1 · 24×1×1;3×1×1 · 7×3×2;2×2×1 · 128×2×1;1×1×2 ·
1×1×1;5×2×1. That is 550 child runs with no failures.

### Large dispatch (`run_agx_sr_scan.py --count 65536`)

The count bound in the C child and the scan runner was raised from 257 to
65536 (2048 X workgroups of 32). Other behavior is unchanged.

### Bit-15 form (`run_agx_sr_scan.py --alt --preload … [--reread]`)

`patch_agx_sr.patch_body` keeps the original index/bounds prefix and
address/store/pop/stop suffix byte-identical, and replaces only the
`mov_imm r2` with an arbitrary body. The preamble relocation is factored out of
`patch_pair` into `_relocate`; patch_pair, patch and patch_even outputs were
checked byte-identical to the previous commit for selectors 80/16/200 and gaps 0/128.
Bodies:

* `mov_imm r2, 0xdeadbeef; get_sr.bit15 r2, SR; wait 0`, for all 256 selectors.
* The same with `wait 1` plus 65 × `wait 0` (selectors 0,4,16,21,32,48,80).
* `mov_imm r2, 0x5a5a1234; get_sr.bit15 r2, SR; wait 0; get_sr r2, SR; wait 0`,
  for all 256, compared with the standard `mov_imm; get_sr; wait` run.

A preload-only control (`mov_imm; wait`) must store the preload exactly before
any selector runs.

## Results

### Workgroup geometry (all nine shapes, both samples, every lane)

| SR | Hardware value | Note |
| --- | --- | --- |
| 0, 1, 2 | workgroup id x, y, z | CUDA `blockIdx` |
| 4, 5, 6 | local size x, y, z | CUDA `blockDim` |
| **7** | **ceil(L / 32)** (1, 2, 8 observed) | SIMD groups per threadgroup; unlabeled |
| 8, 9, 10 | equal SR4/5/6 | Direct dispatch only; no case distinguished them |
| 48, 49, 50 | local id x, y, z | CUDA `threadIdx` |
| 51 | linear local index | |
| 52 | linear local index mod 32 | CUDA `%laneid` |
| 53 | linear local index div 32 | CUDA `%warpid`-like (per block) |
| 56 | index mod 4 | all lanes active here |
| 57 | min(4, L − 4·⌊i/4⌋) | quad population; partial final quad at L=42 → 2 |
| 58 | index mod 32 | all lanes active here |
| 59 | min(32, L − 32·⌊i/32⌋) | partial final SIMD group: L=24 → 24, L=42 → 32,10 |
| 80, 81, 82 | global id x, y, z | |
| 15, 19, 24, 25, 97, 114 | 16, 8, 2, 2, 2048, 136 | Invariant across every shape and 2048 workgroups |

SIMD groups are formed from the **linear** local index (x fastest), not per row.
In the 7×3×2 shape, lane 32 is (4,1,1) and reports SR52 = 0 and SR53 = 1. With
the earlier sparse-mask results, SR57/59 are "active lanes in quad/SIMD group",
and partially filled groups count only existing lanes.

### Core identity (2048 workgroups, three fresh devices)

Driver `core_masks` (retained P1 evidence): `0x3ff, 0x1ff, 0x1ff, 0x3ff`
(10+9+9+10 = 38 cores). In every sample SR20 took exactly 38 values:

```text
0x00-0x09, 0x10-0x18, 0x20-0x28, 0x30-0x39
```

That set equals `{(c << 4) | k : bit k of core_masks[c]}`, and SR20 was
uniform within every workgroup. Per-core workgroup counts were roughly balanced
(1,472–2,048 lanes, i.e. 46–64 workgroups, per core). SR21 was uniform per dispatch (32, 33 and 34
on three fresh devices), consistent with the prior VM-slot observation.

For PTX: `%smid` can be lowered to SR20 directly when sparse ids are acceptable.
A dense 0..37 id needs a remap using the per-cluster masks
(`prefix_popcount(cluster) + popcount(mask[cluster] & ((1<<core)-1))`), and `%nsmid` = 38
on this device. Bits 4+ appear to select the cluster. The 16-slot core field is an
inference from the 4-bit stride; no cluster had more than 10 cores.

### Bit-15 `get_sr` form

* **No destination write.** All 256 selectors × 2 samples × 65 lanes returned the
  preload `0xdeadbeef` unchanged. Adding `wait 1` and 65 `wait 0` did not change
  that for seven representative selectors.
* **No observable SR write.** With `0x5a5a1234` in r2 as a possible source, a
  following standard `get_sr` of the same selector returned exactly the values of the
  standard-only baseline for 255/256 selectors. SR21 differed only by its known
  per-device value (54/55 vs 49/50). No selector ever returned `0x5a5a1234`.
* No fault, timeout, guard corruption or failed control occurred: 19+ unchanged
  controls per sweep, plus a preload control.

Without preload, the first bit-15 smoke run stored stale register-file contents
(similar per-lane garbage across runs). That run is the evidence that the form does
not write D; it also shows that uninitialized GPRs leak values between dispatches.
The instruction's purpose remains unknown. It could act on fragment/coverage state,
on a different register class, or require context not present in compute. This is
a negative result for one compute context only.

## Limits

* One device, one driver build, compute stage only, direct dispatch only.
* SR8–10 vs SR4–6 remain indistinguishable. Mesa labels them
  `dispatch_threads_per_threadgroup`, which may differ for non-uniform or indirect
  dispatch (not tested).
* Meanings of SR15=16, SR19=8, SR24=SR25=2, SR97=2048, SR114=136 are unresolved.
  Shape and workgroup count do not affect them. The next variable is shader
  resources (threadgroup memory, register count).
* SR20's 4-bit core field is inferred from the stride; per-core scheduling counts
  are incidental, not a scheduler model.
