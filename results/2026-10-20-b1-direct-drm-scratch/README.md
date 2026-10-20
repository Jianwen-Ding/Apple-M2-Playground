# B1: scratch / stack memory on direct DRM works (2026-10-20)

Blocker B1 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: solved.** A hand-built shader using
scratch (stack) memory runs on the M2 Max (G14C B1) through `tests/drm_compute.c`, from 1 SIMD group to 65,536
threads on all 38 cores, with per-thread scratch of 80 and 1,036 dwords, 0 wrong words, 0 hangs, 0 faults.
Hang budget 0/30 before and after. cgroup shmem returned to 0 after each run.

The two earlier direct-DRM attempts stalled because they used a **hand-built helper program**. This run uses
Mesa's own compiled `libagx_helper` (captured from a Mesa submission) and Mesa's exact scratch header.

## 1. Data trace of Mesa (safe)

`trace/asahi_trace.c` is an `LD_PRELOAD` shim: it follows GEM_CREATE / VM_BIND / QUEUE_CREATE and, at every
SUBMIT with a compute command, dumps the command and every bound buffer (read-only mappings; it changes nothing).
Run over `spirv_task.py run spill --size small` (Mesa 25.3.6 Vulkan, functional_ok in both control and traced runs).
`trace/submit-1-manifest.json` is the spilling dispatch:

| Field | Mesa's value | Meaning |
| --- | --- | --- |
| `helper.binary` | 0xfffbc201 | USC-relative address of `libagx_helper` with tag bit 0 |
| `helper.cfg` | 0 | `1 << 16` only when the **preamble** uses scratch |
| `helper.data` | header VA | the scratch header below |
| USC Registers word | `8d 03 14 01` | **Spill size field (bits 18..21) = bucket** = 1 + ceil(log2(ceil(dwords / 8))), max 15 (here 5) |
| CDM launch word 0 | 0x1012 | uniform 1 group, texture state 1 group, preshader 1 group (not scratch-specific) |

`helper-mesa.bin` is the helper: 670 bytes of code ending in `stop` plus Mesa's 8 `trap` padding words. It
loads `hdr->cores[core_index]`, waits on doorbell 32 for requests (sr144 = op, sr146/147 = argument),
answers op 0 (stack alloc) by `map target0, block, 0..3` and doorbell 48 (ack), op 1 (free) by `unmap` and
writes the blocks back, NACKs (doorbell 49) when a core has no free subgroup slot, and exits on op 15.

## 2. Scratch header and buffer layout (as Mesa `src/asahi/lib/agx_scratch.c`, confirmed by the trace)

```
header  @0     u32 subgroups (Mesa: 128), u32 pad,
               cores[128] x 88 bytes: { u64 blocklist VA, u32 alloc_cur, alloc_max, alloc_failed, pad, u32 alloc_count[16] }
               core_id = cluster * next_pow2(cores_per_cluster) + core, present cores only (core_masks)
blocklists     per present core: `subgroups` entries x 16 bytes = 4 x u32 block words
blocks         aligned to the block size; per core: subgroups x count x block_bytes
block word 0 = ((1 << (log4 + 1)) - 1) | (block_VA >> 8);  words 1..3 = 1 | (VA >> 8) of the next blocks, or 0
block_dwords = 8 << (2 * log4);  block_bytes = 128 * block_dwords;  (log4, count) from agx_scratch_get_spill_size
```

**Per-thread addressing inside an allocation** (measured, `gpu/full32-core0-sg0-blocks.bin`): lane-interleaved
4-byte slots, stack growing down from the `stack_adjust` size: byte offset `o` of lane `l` is at
`(adjust_words - 1 - o/4) * 128 + 4 * l` (with `stack_adjust #80`: offset 0 at +0x2780, offset 4 at +0x2700).

## 3. Runs (`tests/drm_compute.c`, new `AGX_SCRATCH_DWORDS`)

`AGX_HELPER_CODE=helper-mesa.bin AGX_SCRATCH_DWORDS=N drm_compute /dev/dri/renderD128 kernel.bin COUNT out.bin REPS 16`.
Each kernel was run in `agx_run` first (same outputs). Kernels (`kernels/build*.py`) use only forms Mesa emitted
(`results/2026-10-18-stack-mesa`): Mesa's exact `stack_adjust` bytes, `stack_store/load i32 x` with an immediate
or a register byte offset. Each thread stores A = 3i+1 and B = 5i+7, clobbers both registers, reloads and writes A+B.

| Kernel | Scratch | Threads x reps | Firmware time / dispatch | Peak subgroups per core | Wrong |
| --- | --- | --- | --- | --- | --- |
| `scratch_rt` (offsets 0, 4) | 80 dwords, bucket 5, 3 blocks x 4 KiB, 57 MiB | 32 x 1 | 18 us | 1 (1 core) | 0 |
| same | same | 65,536 x 4 | 105-127 us | 28, all 38 cores | 0 |
| `scratch_big_4000` (offsets 4000 by register, 0) | 1,036 dwords, bucket 9, 3 blocks x 64 KiB, 912 MiB | 32 x 1 | 20 us | 1 | 0 |
| same | same | 65,536 x 4 | 107-124 us | 27, all 38 cores | 0 |

After every run the header shows alloc_cur 0 on every core and alloc_failed 0: every allocation was freed.
The 1,036-dword kernel's two values lie in different 64 KiB blocks (slots 35 and 1035), so the multi-block map works.

`python3 -I verify.py [--sim path/to/agx_run]` checks all of this offline (12 checks).

## Open

- Preamble scratch (`helper.cfg = 1 << 16`) was not exercised.
- Fewer than 128 subgroups per core (smaller buffers) is untested: a NACK path exists in the helper but its
  effect on the shader is unknown, so runtimes should keep 128.
- B34 (stack access cost, wait groups) and B14 (calls) can now proceed.
