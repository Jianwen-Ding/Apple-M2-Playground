# simd_shuffle takes the read position from the source quad's own index bits, not the reader's

Status: confirmed on one device (M2 Max G14C), direct DRM through zluda_agx, all 32 lanes active, our own clang-built
kernel. 12 programs, every lane predicted exactly by the model below.

## Claim

With a per-thread register index, one `simd_shuffle` makes thread r read **quad `idx(r) >> 2` at position
`OR(idx(t) & 3 for the four threads t of that source quad)`**. The low two bits a reader puts in its own index do not
matter; the threads of the quad being read choose (by OR) which of their lanes everyone reading that quad gets.

The [2026-10-18 shfl result](../2026-10-18-shfl/README.md) says "exact only when its low two bits are the same for all
four lanes of the quad it addresses". That is right, but "the quad it addresses" is easy to read as the reader's quad.
That reading is wrong:

* `idx = ((lane ^ 8) & 28) | ((lane >> 3) & 3)` has the same low bits in every **reading** quad, and one shuffle
  gives 32 of 32 lanes wrong. Lane 0 asks for lane 8 and gets lane 9, because lanes 8-11 hold index low bits 1.
* `idx = 4 * ((5q) mod 8) + (q mod 4)` (q = lane >> 2) is right with one shuffle. Source quad 5q mod 8 holds
  low bits (5q mod 8) mod 4 = q mod 4, exactly the position its readers ask for.

## Implications

* A single shuffle is exact iff, for every reader r, every thread of quad `idx(r) >> 2` holds `idx(r) & 3` in its low
  bits. Inactive threads pass 0 (the backend puts register indices in r0h, zero outside shuffles), so the condition
  stays sufficient under any execution mask. The AGX backend checks it exactly for indices that are functions of the
  thread index (llvm-project `readsNamedThreads`, AGXCodeGenPrepare), and splits all other divergent indices into the
  four quad positions.
* So a shuffle with this restriction delivers at most one value per source quad: 8 distinct values. Any gather where
  the 32 lanes need 32 distinct values (a lane permutation) needs the 4-way split, about 11 instructions per
  register.
* `simd_shuffle_xor` with a **constant** mask is an exact single instruction for every lane permutation `lane ^ c`
  ([2026-10-18](../2026-10-18-shfl/README.md)). Layout changes that are bit permutations of the lane index (every mma
  fragment layout) are therefore cheaper as exchanges of two index bits: one `shuffle_xor(v, 2^i | 2^j)` and a select
  per register. ZLUDA's fast mma does this (agx_matrix.rs `bit_move`), and its mma loop went from 345 to 100
  instructions, 2.2-3.3x faster.

## Reproducer and evidence

`results/2026-11-08-shuffle-source-quad/quad_index.cu` (zcc, `%laneid` index functions f = 0..3, 1-3 chained shuffles),
run as `ZLUDA_AGX_LLVM_ARGS=-agx-unsplit-shuffles` (one simd_shuffle per `__shfl_sync`, experiments only) and with
default splitting. [Evidence](../../results/2026-11-08-shuffle-source-quad/hardware.txt): unsplit, f = 2 and 3 are
wrong in 24-32 lanes and match the source-quad model in all 32 lanes of every case. f = 0 and 1 are right. Split, all
are right.
