# Sparse-mask shuffle indices must be initialized outside divergence

Confirmed on M2 Max G14C B1 (generation 14, variant C, revision 17), compute,
direct DRM, AC power, kernel `6.19.14-400.asahi.fc42.aarch64+16k`. Two retained
sweeps: **236 variant dispatches, zero faults**, with independent random inputs.
No timing or rendezvous behavior is inferred.

AGX's shuffle takes its low source-index bits from the OR of **all four lanes'
index operands in the source quad, including inactive lanes**. This rule was
already [published](https://dougallj.github.io/applegpu/docs.html#simd_shuffle).
The new observation is its effect on our proposed PTX lowering: the four-shuffle
sequence validated with a full mask on 2026-10-18 fails under sparse masks
unless inactive lanes' index registers have compatible low bits.

A concrete retained failure: with even lanes active, `shfl.idx` requesting
lane 2 should read that active lane. If inactive neighbours retain index low
bits 1, the quad OR selects lane 3 instead. This corrupts a **defined** PTX
read; it is not merely an unspecified read from an inactive requested source.
Both independent payload words show the error.

## Measured fix and 64-bit lowering

Before entering divergence, initialize the four generic index registers in
**all 32 lanes**:

```text
r19 = 0; r20 = 1; r21 = 2; r22 = 3;
```

Inside the participating mask, compute `ix = p ? j : lane` and the existing
four indices `(ix & 28) | k`. Execute four `simd_shuffle` operations and select
on `ix & 3`, as in the [original lowering](../2026-10-18-shfl/README.md).
Inactive neighbours now contribute the same low bits k. Four all-lane
initializations extend the original 21/22-instruction sequence. Their low bits
must remain valid until the shuffle; initialization inside the divergent arm
is insufficient. Initializing all four registers to zero also passed every
defined comparison, because zero contributes no extra bits to the quad OR.

For a 64-bit CUDA payload, shuffle its two independent 32-bit words using the
same indices and predicate. The generic pair shares index arithmetic, adds
four shuffles plus three selects for the high word, and preserves arbitrary
bits in both halves. The native constant-amount/default-clamp path uses two
immediate-operand shuffles. PTX itself specifies `shfl.sync.b32`; this is a
paired lowering for a 64-bit value, not a claim of a PTX b64 instruction or a
native AGX 64-bit shuffle.

## Evidence

Each sweep runs 118 programs on 96 SIMD groups (3,072 lanes):

| Programs | Variations | Result in both runs |
| --- | --- | --- |
| 48 seeded generic + 2 identical bracketing controls | Four modes; widths 32,16,8,4,2,1; six random clamp/segment encodings per mode | Exact defined data and predicates |
| 52 immediate native pairs | Four modes × amounts 0,1,2,3,4,7,8,15,16,31,32,33,63; amount masked to five bits | Exact defined data and predicates |
| 4 zero-seeded generic controls | One per mode | Exact defined data and predicates |
| 12 poisoned generic controls | Four modes × inactive index low bits 1,2,3 | 4,354 / 4,528 wrong defined data words, as predicted |

The mask set contains empty/full masks, every nonempty proper prefix, every
single active lane, even/odd and scattered quad patterns, and 23 fixed random
masks. All initialization and trace addressing happen before divergence.

There are **180,276 defined positive-case lane results**, each with two payload
words checked: **360,552 exact data words**. The checker separately validates
inactive destination sentinels, all arithmetic predicates, read-only inputs,
table guards, main output guards and patterned tails. Entire raw table
readbacks, including the controlled initialized inactive-source observations,
also match the unmasked-OR AGX oracle and simulator. Bracketing controls repeat
exactly; cgroup shmem starts and ends at zero in each sweep.

Each exact program runs in `agx_run` against a host raw-AGX oracle before its
hardware submission. The retained verifier independently uses the earlier PTX
reference, reconstructs code and input hashes, and rejects missing cases and
corrupted code, inputs, payloads and inactive writes.

## Scope and reproduction

[NVIDIA's PTX definition](https://docs.nvidia.com/cuda/parallel-thread-execution/#data-movement-and-conversion-instructions-shfl-sync)
leaves results unspecified when the requested source is inactive or absent
from membermask. Those data results are excluded from PTX equality counts.
The active hardware mask is the converged participating set. This does **not**
implement `.sync` rendezvous between divergent paths, nor prove that registers
in lanes outside a partial physical launch can be initialized. Non-multiple-of-32
launches, 16-bit shuffle forms and performance remain open. Never use zero from
an inactive source as a defined PTX result based on this experiment.

```sh
python3 -B scripts/run_drm_shfl_mask.py offline --output NEW_SCRATCH_DIR
python3 -B scripts/run_drm_shfl_mask.py hardware --seed 113 --output NEW_SCRATCH_DIR
python3 -B scripts/run_drm_shfl_mask.py hardware --seed 509 --output ANOTHER_NEW_DIR
make verify-shfl-mask
```

[Retained records and layout](../../results/2026-10-20-shfl-mask/README.md).
`verify_shfl_mask.py --no-sim` checks retained evidence without simulator replay.
