# B39: largest allocation and address range (2026-10-21)

Blocker B39 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C, 64 GiB), direct DRM through
agx_runtime, battery power. 0 faults; hang budget unchanged.

**Result: no limit below physical memory. A single 32 GiB object and 40 GiB in 4 GiB objects bound in one VM, and a
kernel wrote the last page of each correctly. The probe stopped itself at a 10 GiB MemAvailable floor rather than
push the host into memory pressure, so the true failure point (beyond ~50 GiB) was not reached on purpose.**

`b39_alloc.rs DIR SIZES FLOOR` (local agx_runtime example): create + bind + CPU-zero one object per size, run
`count.bin` with its output in the object's last 16 KiB page, check 64 words on the CPU; then add 4 GiB objects while
MemAvailable stays above FLOOR + 4 GiB. `run1.jsonl`, `run2.jsonl`:

| Object | Bind + zero | Last page written by the GPU | MemAvailable before -> with |
| --- | --- | --- | --- |
| 1 GiB | 0.12 s | 64 / 64 | 52.1 -> 51.1 GiB |
| 4 GiB | 0.46 s | 64 / 64 | 52.1 -> 48.2 GiB |
| 16 GiB | 1.91 s | 64 / 64 | 52.3 -> 36.0 GiB |
| **32 GiB** | 3.72 s | 64 / 64 | 52.0 -> 20.4 GiB |
| 4 GiB x 10 = **40 GiB** together | 0.46 s each | 64 / 64 each | 52.3 -> 12.1 GiB |

- **Address space:** `vm_start` 0x4000, `vm_end` 0x7f_ffff_8000 (512 GiB), kernel range at least 512 MiB (agx_runtime
  reserves 32 GiB at the top). With the USC heap at 64 GiB, the data heap spans ~412 GiB of VA: far more than RAM.
- **Accounting:** GEM objects are shmem; once bound (and touched) they come out of MemAvailable one for one. The UAPI
  reports no memory figures at all (`drm_asahi_params_global` has none).
- **For ZLUDA:** `cuMemGetInfo` can report free = MemAvailable (minus a margin; also the cgroup's `memory.max` when
  set) and total = MemTotal (64 GiB here); `cuMemAlloc` should accept anything up to that and turn a failed
  GEM_CREATE / VM_BIND / mmap into `CUDA_ERROR_OUT_OF_MEMORY`. Zeroing costs ~0.12 s per GiB on the CPU (agx_runtime
  zeroes every new object); CUDA does not require zeroed allocations, so that can be dropped for `cuMemAlloc`.
