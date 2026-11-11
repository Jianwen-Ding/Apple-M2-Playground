# The stack helper's per-core allocations only need the kernel's occupancy (2026-11-11)

The scratch buffer given to Mesa's `libagx_helper` has `subgroups` allocations per core (Mesa: 128). The helper's
header counter `alloc_max` records the most allocations a core held at once.

- Blender Cycles' stack kernels (72 GPRs -> 2 * floor(1664 / 144) = 22 SIMD-groups per core by the occupancy rule of
  2026-10-11-occupancy) with a buffer of exactly 22 allocations per core: `alloc_max` = 22 on cores, `alloc_failed` = 0
  over a full 1024^2 64-spp render (~240 syncs read). Rodinia dwt2d (32 slots): at most 18 held; llama.cpp
  flash-attention kernels (12 slots): at most 4.
- So resident groups never exceed the register-file occupancy, and a buffer sized by
  max(simd_groups_per_core) over the stack kernels launched is enough (groups of several kernels: each takes at
  least 1/count of the register file). Cycles' scratch 3.57 GB -> 421 MB.
- Host cost of memory on Asahi (kernel 6.19): ~65 ms/GB to allocate a bound GEM object (VM_BIND or the CPU mmap
  pins and zeroes every 16 KiB page; GEM_CREATE alone is lazy), ~38 ms/GB to free (all in GEM_CLOSE). Creating and
  mapping chunks on 8 threads is no faster.

Code: ZLUDA agx_runtime `Vm::scratch(dwords, groups)`, examples `alloc_time.rs`, `par_alloc.rs`.
