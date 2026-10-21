# B10: the AGX instruction sequence for each PTX memory-ordering operation and scope (2026-10-21)

Blocker B10 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`: "once safe-10's litmus tests are done, list the exact
instruction sequence each scope needs, including `.sys` (safe-10 + B7)". No new GPU run; every row cites the
hardware finding it comes from (all M2 Max G14C, direct DRM, compute). Barrier encodings: **f533** `unknown_barrier_1`,
**f59d** `device_barrier_1`, **f596** `memory_barrier`, f59a / f59e / f503 / f599 unnamed; **coherent** = the
`device_load` / `device_store` form with Mesa u4 = 7 (bits 44-46), normal = u4 = 4. Costs are ns per fence back to
back (`novel-results/2026-10-18-fence-cost`; they depend on the preceding access, see there).

## Table

| PTX | Scope | AGX sequence | Evidence |
| --- | --- | --- | --- |
| `fence.*.cta`, `membar.cta` (threadgroup or device memory, same CTA) | cta | **nothing** | `2026-10-18-tg-litmus` (SB / LB / MP in threadgroup memory: 0 in 72 runs, also without any fence); same-core device pairs never reordered (`2026-10-11-memory-ordering`, `2026-10-18-sb-lb`) |
| `bar.sync` / `barrier.sync` / `__syncthreads` | cta | **0x68** (`threadgroup_barrier`) alone; it orders threadgroup and device memory itself | `2026-10-20-barrier-bits` (0 mismatches with no fence; 212.5 M / 149.9 M without the barrier) |
| `bar.sync id, count` (named / partial) | cta | no hardware form (0x68 byte 1 is inert): emulate | `2026-10-20-barrier-bits` |
| 2x2-SIMD-group block barrier (`agx.block_barrier`) | 4 SIMD groups | **0x78** alone (also partial blocks, divergent flow) | `results/2026-10-20-b16-block-barrier` |
| `st.release.gpu`, `fence.acq_rel.gpu`, `membar.gl`, `__threadfence()` (writer side) | gpu | **f533** before the store (27 ns) | MP: f533 alone or Mesa's 7-barrier sequence give 0; f596 alone 40,000-90,000 violations per 1 M (`2026-10-11-memory-ordering`) |
| `ld.acquire.gpu` (reader side) | gpu | load, **`wait 0`, f59d** before the dependent loads (86 ns) | MP reader: 0 with wait + f59d; 3,328 violations with wait only and normal stores (`2026-10-11-memory-ordering`) |
| `fence.sc.gpu` | gpu | **f533, f59a, f596** in that order (~120 ns); f533 + f59a (~40-65 ns) only if every store it orders is a normal (non-coherent) store | SB: 0 in 40 runs; f533 + f59a leaks 16-64 pairs in 4 of 30 runs with coherent stores; f596 before f533 does not fix it (`2026-10-19-sb-minimal-set`) |
| `atom.release.gpu`, `atom.acq_rel.gpu` | gpu | **f533**, then the atomic | an atomic is not a release: 580,000-810,000 violations without f533, 0 with f533 on the writer + f59d on the reader (`2026-10-18-atomic-release`) |
| `atom.acquire.gpu`, `atom.acq_rel.gpu` (acquire half) | gpu | the atomic, **`wait 0`, f59d** | `2026-10-18-atomic-release` |
| `atom.relaxed.*`, `red.*` | any | the atomic alone (atomic, not ordered) | `2026-10-17-atomic-variants` (contention-atomic), `2026-10-18-atomic-release` |
| `ld.relaxed.gpu`, `ld.volatile.gpu` | gpu | a normal load; no rule measured beyond MP above | none specific (open) |
| `st.release.sys`, `fence.*.sys` writer side, `__threadfence_system()` | sys | **coherent store + f533** | GPU -> CPU mid-dispatch: CPU saw 3,712-4,076 of 4,096 tokens; plain store, plain + f533, coherent alone, plain + Mesa's sequence: only the last token, at command end (`2026-10-16-cpu-gpu-visibility`) |
| `ld.acquire.sys`, `ld.volatile.sys`, reads of host-written mapped memory during a kernel | sys | **f59d + coherent load** (+ `wait 0`); ~0.69 us per read | CPU -> GPU: only this combination saw host writes (425,749 increments); plain, coherent without f59d, f59d + plain, atomics: 0; CPU cache cleans change nothing (`results/2026-10-20-b7-cpu-to-gpu`, `2026-10-11-in-shader-clock`) |
| `atom.*.sys` | sys | f533 + atomic (release); atomic + wait + f59d (acquire); an atomic does **not** see host writes made during the dispatch | B7 (atomic add of 0 never saw CPU writes) |
| kernel boundary, same queue (stream order) | gpu | nothing: the next command sees all writes | `2026-10-18-dispatch-visibility` (0 stale reads in 24 runs); B32 (1,000 dependent commands exact with `cdm_barrier` NONE) |
| kernel boundary, other queue or VM | gpu | a syncobj wait on the producer's point (no cache operation) | `results/2026-10-21-b36-b45-shared-memory` (B45) |
| host <-> device after a command (cuMemcpy, event sync) | sys | nothing beyond the fence wait | B36 (CPU mappings agree after completion) |

## Notes for the backend and ZLUDA

- **Never emit `memory_barrier` (f596) alone for device scope**: it orders nothing across cores. f533 is the release
  fence, f59d the acquire (invalidate) fence; they are cheap (27 / 86 ns) next to Mesa's 7-barrier "big hammer"
  (434 ns).
- **The coherent bit alone does not give `.sys` visibility** in either direction: GPU -> host needs f533 after the
  coherent store, host -> GPU needs f59d before the coherent load.
- **Same core never reorders** in any test, so CTA scope needs no fence even for device memory.
- **Open:** IRIW (multi-copy atomicity) was never tested; `ld.relaxed` has no specific lowering beyond "normal load";
  workgroups of 16 / 64 lanes and more than 8 SIMD groups per core in the SB test; whether the rare f533 + f59a leaks
  with coherent stores are real (the 3-fence form avoids the question).
