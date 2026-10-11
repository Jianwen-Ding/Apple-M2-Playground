# 0x78 is a barrier over aligned blocks of 4 SIMD groups; 0x68 covers the whole workgroup

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
0 faults. This corrects the [earlier finding](../2026-10-11-sync-and-end-opcodes/README.md),
which tested 0x78 only up to 4 SIMD groups and called it a whole-workgroup barrier.

## Claim and scope

**Message-passing stress test.** Every lane writes 8 iteration-tagged values (no `wait`),
then all groups hit barrier A. Each lane reads the 8 values of the lane 32·d positions
later (mod workgroup size), i.e. in a SIMD group d away, and counts mismatches. All groups
then hit barrier B. The loop runs 2,000 iterations over 16,384 threads. Both barriers are
executed by every group in every iteration, so nothing can deadlock. Variants: threadgroup
or device memory; workgroups of 64–1,024 lanes; d = 1, 2, 4; and before barrier A, nothing,
`wait`, `memory_barrier`, or `wait` + `memory_barrier` (Mesa's sequence).

| Barrier | ≤ 4 SIMD groups (64, 128 lanes) | 8–32 SIMD groups (256–1,024 lanes) |
| --- | --- | --- |
| `wait 0` (negative control) | stale reads (where groups do not run in lockstep) | stale reads in every SIMD group |
| **0x68** `threadgroup_barrier` | **0** | **0**, all 39 configurations |
| **0x78** | **0**, all 16 configurations | **stale reads only where the partner is in another aligned block of 4 SIMD groups** |

Where the 0x78 errors appear (lanes with errors per reading SIMD group, device memory, Mesa sequence):

| Workgroup | Partner distance d | Reading groups with errors |
| --- | --- | --- |
| 256 lanes | 1 | 3, 7 |
| 256 lanes | 2 | 2, 3, 6, 7 |
| 256 lanes | 4 | all 8 |
| 512 lanes | 1 | 3, 7, 11, 15 |
| 1,024 lanes | 1 | 3, 7, 11, …, 31 |

Reads within the block of lanes 0–127, 128–255, and so on are always correct. A block-crossing
read is stale in every variant, including Mesa's `wait` + `memory_barrier`, so adding a memory
barrier does not widen 0x78's scope. **0x78 is a barrier over the aligned group of 4 SIMD
groups (128 threads)**, and 0x68 is a barrier over the whole workgroup. Both make device- and
threadgroup-memory writes visible within their scope.

### Trade-off

| | 0x68 | 0x78 |
| --- | --- | --- |
| Scope | whole workgroup (tested to 1,024 lanes) | aligned 4-SIMD-group block (128 lanes) |
| Cost per use, one SIMD group | 9.3 ns | 2.9 ns |
| Correct as `__syncthreads()` | always | **only if blockDim ≤ 128** |

A plausible reading (an inference, not tested) is that 4 SIMD groups map to one of the core's
four sub-schedulers, and 0x78 synchronizes only within one. For workgroups of 128 lanes or fewer,
0x78 gave identical results to 0x68 in every test. At kernel level the saving was small: the
128-lane threadgroup-memory runs took 6.80–7.10 ms with 0x78 and 6.46–7.10 ms with 0x68.

### Side finding: usable threadgroup memory = declared bytes ÷ 4

With the USC Shared word `0x4d | 1<<8 | 0x24<<10 | (bytes/256)<<24` and i32
`threadgroup_load/store` packed as in Mesa, a 64-lane exchange is exact **iff every touched
byte is below declared/4**: 2,048 of 8 KiB, 4,096 of 16 KiB, 8,192 of 32 KiB (23/23 cases).
Beyond that, loads return 0. Either the size field counts 64-byte units, not Mesa's 256, or
each i32 element occupies 16 bytes. This experiment cannot tell which. Until that is resolved,
declare 4× the shared memory a kernel touches. The first stress run declared 8 KiB for
8 KiB of data, and 0x68 and 0x78 failed *identically* at 128/256 lanes. That was this artifact,
not a barrier effect (kept as `matrix-shared8k.json`).

## Reproducer and evidence

`make barrier-stress` (hardware), `make test-barrier-stress` (hardware subset;
[test](../../tests/test_barrier_stress.py)), `make verify-barrier-stress` (14 offline checks),
`scripts/run_drm_tg_capacity.py` (capacity probe).
[Evidence](../../results/2026-10-11-barrier-0x68-vs-0x78/README.md).

## Relationship to existing knowledge

Mesa emits only 0x68 for workgroup barriers (`agx_compile.c:1544-1549`, via Copilot's
analysis), and nothing for SIMD-group scope. Neither Mesa nor applegpu names 0x78. Mesa
packs the shared size as `groups(256)` (`cmdbuf.xml:696`). The ÷4 capacity result therefore
disagrees with Mesa's apparent units, or with this harness's element addressing. It needs
a Mesa-compiled shader for comparison.

## Compiler implications and limitations

* Lower PTX `bar.sync` / `__syncthreads()` to **0x68**. 0x78 is valid only when the launch's
  block size is known to be ≤ 128 threads, which a compiler rarely knows. If used, it saves about
  6 ns per barrier per SIMD group.
* 0x78 could implement a cheaper barrier for cooperative groups of 128 threads (4 warps).
  There is no direct PTX equivalent: `bar.sync` with a thread count uses named barriers,
  which are not mapped yet.
* Size threadgroup memory as 4× the bytes used until the ÷4 question is resolved, and check
  how Mesa's own compute kernels address shared memory.
* Not tested: barrier counts that differ between groups (deadlock risk), fragment shaders,
  workgroup shapes other than 1-D.
