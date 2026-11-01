# Asahi GEM objects are allocated and zeroed when they are created

Status: confirmed on one device (M2 Max G14C, 64 GB, kernel 6.19.14-400.asahi.fc42.aarch64+16k), direct DRM ioctls,
no GPU work. A property of the open source Asahi kernel driver on this machine, measured from user space; nothing
was disassembled or decompiled.

## Claim

1. A new GEM object (`DRM_IOCTL_ASAHI_GEM_CREATE`, `DRM_ASAHI_GEM_WRITEBACK`) reads as zeros, including when its
   pages are recycled from objects that were just written and freed: 16 rounds of allocate (4 KiB to 512 MiB),
   check every byte, fill with 0xa5, free, with every new object all zeros.
2. Creation is eager: a 512 MiB object takes ~20 ms to create even unbound (~26 GB/s, the rate of zeroing the
   memory), so physical memory is committed at allocation, not at first use.
3. Binding it into the GPU VM (`DRM_IOCTL_ASAHI_VM_BIND`) adds ~15 ms per 512 MiB (create + mmap + bind: 34.9-36.2 ms).
4. The CPU mapping faults in page by page: the first touch of each 16 KiB page of a 512 MiB object costs ~20.7 ms
   in all (~0.63 us per page).

## Runtime implication (zluda_agx / agx_runtime)

- A CPU zero fill after creation is redundant and costs the page faults plus a second pass: removed (ZLUDA
  3fdad96; 512 MiB allocation 57-59 ms -> 35-36 ms, 64 MiB 10.8-11.3 ms -> 5.1 ms; `AGX_ZERO_ALLOC=1` restores it).
- `cuMemAlloc` cannot be made lazy from user space: an allocation commits and zeroes its memory immediately. A
  program that allocates more than it uses pays in physical memory; a caching allocator (re-use of freed objects)
  would save the ~20 ms per 512 MiB of a create-free churn.
- The CPU's first access to a fresh object is slow (page faults); copies into new allocations pay it once.

## Reproducer and evidence

`cargo run --release -p agx_runtime --example zero_check [ROUNDS]` in ZLUDA (branch claude/perf-air-agx).
[Evidence](../../results/2026-11-01-gem-zeroed-pages/hardware.txt).
