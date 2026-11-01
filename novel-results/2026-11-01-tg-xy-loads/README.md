# A threadgroup load of two words per lane costs the same as one word (~32 core cycles per load per SIMD-group)

Status: confirmed on one device (M2 Max G14C), direct DRM, AGX Performance Simulator `scripts/mem_probes.py`.

## Claim

One SIMD-group issuing 8 independent `threadgroup_load` instructions then `wait 0`, in a loop: core cycles per load

| lanes' addresses | 1 group: x / xy | 4 groups: x / xy |
|---|---|---|
| all lanes one word (broadcast) | 30.9 / 32.0 | 31.3 / 32.3 |
| consecutive words | 30.9 / 32.1 | 31.4 / 32.3 |
| two words apart (xy: each lane its own pair) | 31.9 / 33.0 | 36.8 / 33.3 |

`xy` (a register pair from two consecutive words) costs one load's time: the per-group threadgroup path moves 64
words in one ~32-cycle slot. Broadcast is no cheaper than distinct words. Extends the 2026-10-11 x-only sweep
(simulator results/2026-10-11-memory-hierarchy/tg.json).

## Implications

- Kernels should load threadgroup data as pairs (or wider) where they can: twice the data for the same slot.
- Threadgroup load cost is not what makes tiled GEMMs with few groups per core slow; the simulator's +42% on
  Geekbench's gemm_block_size_bias is a deferral rule (simulator results/2026-11-01-tg-xy-and-settle).

## Reproducer and evidence

`python3 scripts/mem_probes.py run --kind tgload_xy --groups 1,4 --stride 0,1,2` (and `--kind tgload`) in
AGX-Performance-Simulator; rows in its results/2026-11-01-tg-xy-and-settle/tgxy-*.json.
