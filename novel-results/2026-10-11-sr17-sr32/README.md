# SR17 hardware SIMD-group slot, SR32 pipeline offset, and the preshader-last rule

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.

## Claim and scope

* **SR32** = USC offset of the dispatch's pipeline words (CDM launch word 1). It
  follows 5 placements exactly and ignores the code offset.
* **SR17** = per-core hardware SIMD-group slot. It is uniform per SIMD group and
  equals SR53 under light load, but takes 30–40 values per core with 2,048
  one-SIMD workgroups while SR53 stays 0. Its range shrinks with register
  allocation.
* **SR113** is random (0 or 8).
* **The (No) preshader word must be the last USC pipeline word.** Otherwise the
  dispatch silently executes nothing.

Not established: an occupancy formula from SR17 (distinct IDs ≠ peak concurrency)
and the meaning of SR15/24/25/97/114.

## Reproducer and evidence

`make sr-direct` (hardware), `make verify-sr-direct` (10 offline checks).
[Report](../../experiments/registers/sr-direct-drm.md) ·
[evidence](../../results/2026-10-11-sr-direct-drm/README.md).

## Relationship to existing knowledge

Mesa's register list has no name for SR17 or SR32. The earlier
[Vulkan scan](../../experiments/registers/special-register-scan.md) saw SR32 step by
0x24000 per command buffer and never saw SR17 nonzero, because one SIMD group per
workgroup at light load gives slot 0. The preshader-last rule is consistent with
Mesa always emitting that word last (`hk_shader.c`), which it never documents as
a requirement.

## Compiler implications and limitations

PTX `%warpid` can map to SR17, which, like NVIDIA's, is a volatile hardware slot.
The stable per-block warp index stays SR53. SR32 offers a shader-visible pipeline
identifier with no obvious CUDA use. Runtimes building USC words by hand must end
them with the preshader word.
