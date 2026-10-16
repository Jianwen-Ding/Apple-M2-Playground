# The direct-DRM interface on Asahi (M2 Max, kernel 6.19.14-400.asahi)

Everything between "AGX machine code in a file" and "the GPU ran it", as used by `tests/drm_compute.c` (simulator
copy: `AGX-Performance-Simulator/tests/drm_compute.c`). This is the base the Stage 3 CUDA runtime will build on.

**Sources:**
- the installed header `/usr/include/drm/asahi_drm.h` (kernel-headers 6.19.6). It is the same UAPI as upstream
  mainline; see `docs/external-knowledge.md`.
- Mesa genxml field names (`AGX_Probe/mesa/src/asahi/genxml`);
- the measurements linked below.

Simulator task `safe-12` tracks the remaining open items.

## 1. Ioctls

| Ioctl | Used by `drm_compute` | What it does / what we measured |
|---|---|---|
| `GET_PARAMS` | yes | Fills `drm_asahi_params_global` (592 bytes). `param_group` must be 0 (1 → EINVAL). A shorter `size` is honoured exactly: 8 bytes wrote only `features`. A larger buffer is accepted. Values in §2. |
| `GET_TIME` | yes | Returns the GPU timestamp counter in ns (1 GHz, same timebase as command timestamps). `flags` must be 0 (EINVAL). |
| `VM_CREATE` | yes | Creates a GPU address space. The caller supplies the kernel carve-out `[kernel_start, kernel_end)` inside the VA window, at least `vm_kernel_min_size` (512 MiB). One page, a range outside the window, or a flipped range → EINVAL. ≥ 256 VMs per process (cap of the probe, not reached). |
| `VM_DESTROY` | yes | |
| `GEM_CREATE` | yes | Creates a buffer object (BO). Flags: `WRITEBACK` (CPU-cached mapping; the harness always uses it) and `VM_PRIVATE` (requires `vm_id`; a `vm_id` without `VM_PRIVATE` → EINVAL). Unknown flag bits → EINVAL. Size 0 → ENOSPC. A size that is not a multiple of 16 KiB is accepted. Creation pins no memory: 64 GiB succeeds (the probe's cap). |
| `GEM_MMAP_OFFSET` | yes | Fake offset for `mmap` of the BO on the DRM fd. |
| `VM_BIND` | yes | Maps or unmaps BO ranges. Rules: |
| | | • READ and/or WRITE is required (neither → EINVAL). |
| | | • VA, offset and range must be 16 KiB aligned (4 KiB → EINVAL). |
| | | • Range past the BO → EINVAL. |
| | | • VA must lie in `[vm_start, kernel_start)`: the kernel carve-out and `vm_end` → EINVAL. |
| | | • Binding over an already bound range succeeds (replaces the mapping). Unbinding an unmapped range succeeds. |
| | | • `SINGLE_PAGE` maps one BO page repeatedly: 64 GiB of VA with one physical page succeeded. |
| | | • A regular pinned bind of 4 GiB succeeded (probe cap). |
| | | • Unknown flag bit 4 → EINVAL. |
| `GEM_BIND_OBJECT` | yes | Binds a BO as a timestamp buffer (`USAGE_TIMESTAMPS`). Returns an `object_handle` that commands reference for start / end timestamps. |
| `QUEUE_CREATE` | yes | Creates a firmware queue on a VM, with `usc_exec_base` (the base for USC-relative shader addresses). Priority 0 (LOW) and 1 (MEDIUM) work. 2 and 3 are "reserved" and return **EINVAL** (not EPERM), and so does 4. `flags` ≠ 0 → EINVAL. Unknown VM → ENOENT. ≥ 64 queues on one VM (probe cap). |
| `QUEUE_DESTROY` | yes | Unknown queue → ENOENT. |
| `SUBMIT` | yes | One command buffer of `{drm_asahi_cmd_header, payload}` records plus a `drm_asahi_sync` array (the first `in_sync_count` are waits, the next `out_sync_count` are signals). The harness signals one binary syncobj and waits on it with `DRM_IOCTL_SYNCOBJ_WAIT` (3 s). |

Generic DRM ioctls used: `SYNCOBJ_CREATE`, `SYNCOBJ_WAIT`, `SYNCOBJ_RESET`, `GEM_CLOSE`.
Unused so far:
- timeline syncobjs;
- `in_sync` waits;
- render commands (`CMD_RENDER`);
- attachment commands (`SET_*_ATTACHMENTS`).

## 2. Device parameters (`GET_PARAMS`)

| Field | Value | Meaning |
|---|---|---|
| `gpu_generation` / `variant` / `revision` | 14 / 'C' / 0x11 | G14C B1 |
| `chip_id` | 0x6021 | T6021 (M2 Max) |
| `num_dies` / `num_clusters_total` / `num_cores_per_cluster` | 1 / 4 / 10 | 40 logical core slots |
| `core_masks` | 0x3ff, 0x1ff, 0x1ff, 0x3ff | 38 enabled cores. Cluster c, core k → SR20 = (c << 4) \| k (`novel-results/2026-10-10-sr-geometry-core-id`). |
| `max_frequency_khz` | 1,398,000 | 1.398 GHz |
| `features` | 1 | **SOFT_FAULTS**: shader loads from unmapped VA return 0, and stores to it are dropped. This applies only to shader load / store, not to textures or other units. |
| `vm_start` / `vm_end` | 0x4000 / 2^39 − 32 KiB | 512 GiB VA window |
| `vm_kernel_min_size` | 512 MiB | minimum kernel carve-out (the harness uses 32 GiB at the top) |
| `max_commands_per_submission` | 64 | firmware limit per SUBMIT |
| `max_attachments` | 16 | per command (render) |
| `command_timestamp_frequency_hz` | 10^9 | firmware command timestamps are in ns |

Soft faults matter for CUDA:
- an out-of-bounds global access silently reads 0 instead of faulting, so `cuda-memcheck`-style detection needs
  explicit bounds checks;
- a compiler may speculate loads.

## 3. One compute dispatch, word by word (as `drm_compute` builds it)

### Memory layout

- The VA layout follows Mesa:
  - USC (shader) BO at the first 4 GiB-aligned address ≥ 2^36, which is also the queue's `usc_exec_base`;
  - data BO 4 GiB above it;
  - a 16 KiB timestamp BO;
  - kernel carve-out: the top 32 GiB.
- **USC BO** (shader addresses are USC-relative, i.e. BO offsets):
  - `0x1000`: pipeline words;
  - `0x2000`: main code;
  - `usc_words + 0x200`: optional preamble;
  - `0x4000`: optional helper program.
- **Data BO:**
  - `0x0`: the uniform source (u4 = 0, u5 = count, u6_u7 = output VA, u8_u9 = table VA);
  - `0x4000`: the CDM control stream;
  - `0x6000`: optional sampler heap;
  - `0x8000`: output (8 guard words, payload, 8 guard words, 16 pattern words);
  - 1 MiB: optional table.

### USC pipeline words (`AGX_USC_ORDER`, default `ushrn`)

| Word | Bytes | Fields (Mesa genxml name) | Measured effect |
|---|---|---|---|
| Uniform | 8 | tag 0x1d; start (halves) = 8 → u4; size = 12 halves (u4..u9); buffer VA >> 2 at bit 26 | copies the uniform source into u4..u9 before the shader runs |
| Shared | 4 | tag 0x4d; layout 0x24 at bit 10 (vertex / compute); bytes / 256 (0 = all 64 KiB); sample stride; imageblock w / h | SR18 = bytes field × 256; SR12 / SR13 = imageblock w / h; SR15 = sample stride (0 reads as 16); threadgroup memory per workgroup → occupancy floor(65536 / bytes) |
| Shader | 6 | tag 0x0d; `unk_2` = 3 at bit 10 (Mesa's compute value); code offset at bit 16 | entry point |
| Registers | 4 | tag 0x8d; register count / 8 at bit 8 (5 bits, 0 = 256); `unk_4` = 1 at bit 24 | SR19 = allocation; occupancy min(96, 2·floor(3328 / (2·halves))). The count 256 wraps to 0: never launch it. |
| No preshader / Preshader | 2 / 8 | tag 0x88 / tag 0x38 + 0xc08000 + preamble offset | the preamble runs once per core, one lane, slot 96, SR24 = 5 (`novel-results/2026-10-11-preshader-execution`) |

### CDM control stream

| Word | Value | Meaning |
|---|---|---|
| Launch 0 | `1 << 1` (\| `AGX_WORD0_OR`) | uniform-count groups (of 64) = 1; direct launch; block type 0 |
| Launch 1 | USC offset of the pipeline words | 64 B aligned |
| (G14X only: 4 clusters) | `0`, `1 << 30` | extra launch words for multi-cluster parts (Mesa's G14X form) |
| Global size | 3 × u32 | threads in X / Y / Z (≤ 2^30 total) |
| Local size | 3 × u32 | workgroup size (≤ 1024) |
| Barrier | `3 << 29 \| 0xfffff` | Mesa's barrier with unk0..19 set, including the USC cache invalidate |
| Terminate | `2 << 29`, 0 | end of stream |

### Command and completion

- `drm_asahi_cmd_compute` holds:
  - `cdm_ctrl_stream_base` / `end`;
  - `sampler_count` / `sampler_heap`;
  - `helper` {binary, cfg, data};
  - `ts.start` / `ts.end` (timestamp-object handle + offset).
- The header sets `vdm_barrier = NONE` and `cdm_barrier = 0` (wait for the previous compute command in this queue).
- Firmware writes start / end timestamps in ns (1 GHz).

### Unexplained fields (never flip them by hand)

- Launch word 0 bits other than the uniform count;
- the G14X extra words;
- the barrier's unk0..19 individually;
- Shader `unk_2`;
- Registers `unk_4`;
- Preshader `0xc08000`;
- the helper program `cfg`.

Helper programs stalled the GPU twice (`notes/failed-approaches.md`). Do not use them.

## 4. Open (simulator task safe-12)

- **Sync primitives:** a second submission that waits (`in_sync`) on the first's syncobj, with the control kernel
  only, to confirm ordering from firmware timestamps. Also timeline syncobjs. This is how CUDA events and
  `cudaStreamWaitEvent` would map.
- **Several dispatches per command / commands per SUBMIT:** ≤ 64 commands (safe-04 §4).
- **Userptr import:** the UAPI has no userptr ioctl. CPU memory must come from a GEM BO mapped into the process, so
  CUDA "unified memory" maps to WRITEBACK BOs (see safe-03 §4 for visibility).

## Reproduce

`make drm-limits` (ioctls only; no SUBMIT is issued) and `make verify-drm-interface` (offline, 24 checks against
`results/2026-10-16-drm-interface/drm-limits.jsonl`).
