# G14C B1 special-register scan and mask behavior

**Hardware result:** all 256 selectors completed three single-read samples at
257 active invocations. A second full sweep read each selector twice per lane,
with 128 explicit integer adds between reads, at 16 active invocations and
three samples. Every paired value was identical. **No progressing timing
register was found through this 32-bit `get_sr` access path.**

The scan also found reproducible lane/mask behaviors, including selectors not
named in the supplied applegpu map. They are new observations in this project;
we do not claim first discovery by the community. All selected successful runs
verify offline: **2,522 full readbacks / 435,904 uint32 words**.

## Reproduce

```sh
make sr-scan        # 0..255, three samples, 257 invocations
make sr-pairs       # 0..255, two reads/lane with 128 adds, 16 invocations
make sr-characterize # fifteen active-count boundaries for selected registers
make sr-even        # sparse even-index execution mask
make sr-context     # twelve dispatches per selector in one logical device
make verify-sr      # retained evidence and failure-injection checks, no GPU
```

The isolated Vulkan runtime must already exist under
`/scratch/apple-m2-playground/vulkan-runtime/usr/lib64`; the existing
`scripts/run_vulkan_caps.py --setup` can restore its pinned signed dependency.
This session restored that dependency without changing global packages or
vendor trees. Header/driver/UUID requirements are the same as the
[native instruction baseline](../arithmetic/first-agx-instruction.md).
Standalone runners accept selector subsets; `run_agx_sr_scan.py --help` lists
count, sample, spacing, pair gap, failure budget and output options. The context
runner also accepts `--count` and `--selectors`.

## Data-only single-read scaffold

The control blob SHA256 remains
`b79bd25941bdea1a0095b219fe0333ac5c18822225de811c9308a38702e9e098`.
At blob `0x952` / code `0x96`, replace six-byte `mov_imm r2, 0x12345678`
with four-byte `get_sr r2, selector` and two-byte `wait 0` (`3800`). All
non-digest changes remain within those six bytes. Destination r2 feeds only
the guarded store's data; index r1, descriptor base u6_u7, bounds and execution
mask remain untouched. SHA1 wrapper integrity is refreshed and rechecked.

Independent selector encoding:

```text
raw = 0x72 | (2 << 7) | (4 << 9)
      | ((selector & 63) << 16) | ((selector >> 6) << 26)
```

The pinned model verifies the four-byte instruction and exact destination/SR
fields. Known position/dimension selectors then establish the hardware read and
store path: SR80 returns global X, SR0 workgroup X, SR4 returns 32, SR5/6 return
1, SR48/51/52 return local index 0..31, and SR53 returns zero in these 32-thread
workgroups. Model labels are not substituted for untested hardware behavior.

Single samples use fresh child/device contexts and 20 ms requested spacing.
Every 16 selectors, plus before and after, the unchanged constant shader must
pass its full oracle. Each child is bounded to 15 seconds (build: 30 seconds);
the Vulkan child waits at most three seconds for its fence. A failed selector
would be recorded without retry; continuation requires a passing unchanged
recovery control, and a finite failure budget applies. All full sweeps and
characterization runs completed without observed import/completion failures,
timeouts or guard corruption. Reset telemetry was not independently collected.

## Same-shader paired reads

The paired main stores at indices `8+2*i` and `9+2*i`, so its active count is
bounded to 16 within the unchanged child's 32-word payload allocation. It uses
the same registers, descriptors, outer bound, and store encoding. Between reads
it completes the first store and executes exactly 128 uncompiled native
`iadd r2, 1, r2.sx` instructions. The second SR read replaces that scratch value.

The larger main relocates the unchanged preamble to an aligned offset. Only the
measured code/main sizes, preamble offset, wrapper length and SHA1 are adjusted;
rodata, register allocation and other metadata remain unchanged. Original main
size is 70 bytes, comprising 54 executable bytes and 16 bytes following stop.
Rebuilt constant controls and known SR80/48 paired oracles validate this scaffold
before unknown selectors. The independent verifier reconstructs every byte.

Across **12,288 paired lane observations**, first and second values matched.
This is a negative result for this read path and setup. No timer frequency,
cycle count, clock domain, ordering guarantee, or latency is inferred from the
128-add gap. Other instructions, register widths, stages or enabling state
could expose a clock not observed here.

## Lane and active-mask findings

Fifteen active counts were tested twice each:
`1,2,3,4,5,7,16,17,31,32,33,63,64,65,257`.
A separate sparse test keeps the original bound but adds a nested even-index
predicate before the SR read and store. Odd output slots stay sentinels. Sparse
constant and SR80/0/48 controls establish the predicate and addressing before
interpreting unknown outputs. Count 33 was repeated three times.

| Selector | Contiguous active prefix | Sparse even indices, first 32-lane block | Supported description |
| --- | --- | --- | --- |
| SR16 | `i mod 4` | active lanes report `0,2,0,2,...` | Physical lane position within four-lane blocks in this layout |
| SR56 | `i mod 4` | `0,1,0,1,...` among active lanes | Packed active position within four-lane blocks |
| SR57 | Number of active lanes in the containing four-lane block | 2; final singleton block gives 1 | Active population of a four-lane block |
| SR58 | `i mod 32` | `0,1,2,...,15` among active lanes | Packed active position within 32-lane blocks |
| SR59 | Number of active lanes in the containing 32-lane block | 16; final singleton block gives 1 | Active population of a 32-lane block |
| SR60 | Always 15 | Still 15 | Not the current sparse execution mask in these compute tests |

For example, at active count 7, SR57 returns `[4,4,4,4,3,3,3]`, while
SR59 returns seven copies of 7. Under the even mask, physical lanes 0 and 2
return SR16 values 0 and 2, but SR56 values 0 and 1. These distinctions are
hardware observations, verified from complete raw buffers. General geometry,
non-X layouts, fragment/helper lanes and all possible masks remain untested.

## Other values and the clock search

Thirty selectors returned at least one nonzero value in the initial full sweep:
`0,4,5,6,7,8,9,10,15,16,19,20,21,24,25,32,48,51,52,56,57,58,59,60,63,80,97,113,114`.
The other 226 returned zero in that state. Zero does not establish an absent or
unimplemented register. SR20 matched workgroup numbering in the observed small
dispatches; this does not distinguish its source-labeled core identity from
scheduling coincidences.

Unnamed fixed outputs included SR7=1, SR15=16, SR19=8, SR24/25=2,
SR97=2048 and SR114=136. Their meaning is unresolved. SR8/9/10 matched 32/1/1
here, but no independent workgroup-shape variation was performed.

SR21 changed between freshly created devices (50,51,52 in the full sweep),
but stayed at 47 across twelve dispatches with 10 ms requested spacing in one
context. The initial paired sweep likewise had no intra-shader change. This
supports context-related state, consistent with the existing VM-slot label;
it is not a progressing clock.

SR32 began at `0xfff88000` and decreased by exactly `0x24000` between successive
new command buffers in one context. Follow-ups at counts 1,33,65 and257 all
showed the same step, so it did not scale with workgroup count. It remained
unchanged between paired reads. Allocation/address-related state is a hypothesis,
not an identified pointer or timer; each repeated dispatch allocates a new
command buffer, which is an explicit confounder.

SR113 was 8 once and then zero in the initial sweep; it was zero throughout
the paired sweep, and changed from zero to 8 on the last of twelve same-context
dispatches. This intermittent state is not a clock signature. No selector showed
progression between the separated reads, so no timing register is identified.

## Evidence and provenance

[Retained records and snapshots](../../results/2026-10-04-sr-scan/README.md)
include full raw readback hex, shader reconstruction fields, exact hashes,
API events, command bounds/host brackets, original source snapshots and all
count/context tests. [Scoped lane finding](../../novel-results/2026-10-04-sr-lane-behavior/README.md)
links the independent mathematical oracle.
[Copilot review](sr-copilot-review.md) covers executed hardware records without
claiming that source inspection discovers a clock. Integration subsequently
corrected sparse-control validation and aggregate pair-delta reporting.

Unknown-selector scanning was explicitly requested by the project owner in this
session, superseding the older source-admission guidance. The task used hardware
readback to characterize values; driver/decoder source served as transport and
encoding scaffolding. Paid acm-dev workers failed on funding, and a free worker
produced no report before termination. Copilot completed the offline reviews and
verifier; the coordinator performed all serialized hardware execution.
