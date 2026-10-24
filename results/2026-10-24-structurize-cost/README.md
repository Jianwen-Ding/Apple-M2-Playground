# Legacy structurization analysis and large-shader costs

LLVM checkpoint `2f73959ea7b7` makes legacy StructurizeCFG uniformity analysis
conditional on its effective skip-uniform-regions setting. AGX normally
structurizes every region, so the previous eager analysis was unused. When
skipping is requested, the replacement computes uniformity from the original
function before its first region rewrite, retains it across regions, and
resets it between functions. The new pass-manager implementation already
handles this condition. No shader instruction selection or ISA encoding was
changed.

## Validation and measured limits

The LLVM suites pass 103 available tests: 78 AGX and 25 generic
structurization tests. Three AMDGPU-only tests are unsupported in this build.
The new regression checks scheduling, the library-option override, divergent
branches, and analysis lifetime across multiple functions. The matching
simulator checkpoint is `1fd2a96`: twenty output checks pass across G13G/G14C
and both option settings; generated code, execution and predicted cost agree
between each pair. Its reproduction script and full numeric records are in
`AGX-Performance-Simulator/results/2026-10-24-structurize-analysis`.

Blender camera-only IR: six alternating, otherwise idle compilations with a
freshly rebuilt baseline and changed compiler give median wall times
0.426875 / 0.426232 seconds. This is essentially unchanged. All six live text
sections are identical, 44,222 bytes, SHA-256
`48252ea19c0650f3a52e3011fa461e42f44df469d7d5964a8eabb9fa17c694ba`.
The baseline uniformity pass accounts for only about 0.5 ms for this fixture.
See `camera-structurize-fresh-timing.json`. Earlier comparisons against an
older frozen compiler and one overlapped build are not the controlled result.

The deployed zoc was relinked with the changed LLVM archives. Supplied Qwen
counting inference exits zero, matches the CPU output exactly, and takes
17.742 seconds with 39 compiler invocations. A concurrent LLVM rebuild makes
this a correctness check, not a controlled timing comparison. The hardware
CUDA smoke test has zero incorrect outputs across 50,000 vector elements,
graph replay, unified memory and 2D copy checks. See `structurize-qwen.json`
and `structurize-smoke.json`.

Full Blender surface compilation remains unresolved. Stopping after
structurization reaches the 120-second observation timeout both before and
after this analysis change. No Blender render or overall application speedup
is established by this checkpoint.

## Findings that determine the next action

Changing the existing `-max-booleans-in-control-flow-hub` option from 32 to 0
does not materially change loop-exit normalization: the pass remains near
4.15 seconds. Before-structurization wall times are 31.560 / 31.013 seconds,
mostly including other passes and intermediate IR serialization. The setting
was left unchanged. Commands and pass profiles are retained here.

Temporary instrumentation around the legacy region pass manager separates
its transformation, verification, and node-cache clearing. The changed
compiler was stopped after 100 seconds. At the last periodic sample, it had
processed 67,000 regions and accumulated:

| Operation | Cumulative seconds |
| --- | ---: |
| Region transformations | 58.856 |
| Region verification | 0.00345 |
| Preserved-analysis verification | 0.0560 |
| Clearing region-node caches | 23.484 |

These are incomplete, instrumented measurements; they are not full compile
times or a speedup. They identify a concrete next optimization target:
`RGPassManager::runOnFunction` clears the entire region tree after every
processed region. `RegionBase::clearNodeCache` recursively visits even empty
caches. Any replacement must preserve cache invalidation when regions and
edges change, including parents and subregions. No change to this behavior
has been enabled yet.

The diagnostic patch is `region-profile.patch`; apply it only to a disposable
LLVM checkout based on the recorded checkpoint and rebuild llc. Reproduce
with:

```bash
AGX_REGION_PROFILE=1 llc -mtriple=agx -mcpu=agx-g14c \
  -stop-after=structurizecfg -time-passes -o /dev/null \
  /scratch/blender-ir-profile/module.surface-only.ll
```

Use a 100-second external timeout for the reported observation interval.
The columns in each AGXREGION line are count, transformation seconds, region
verification seconds, preserved-analysis verification seconds, and cache
clearing seconds. `surface-region-profile.log` and `region-profile-summary.json`
retain the measurements. The patch is absent from the production source and
deployed compiler; both scratch source files were restored and the standard
llc/opt rebuilt. No assertion or verification check was disabled.

## Geekbench application validation

Geekbench 7.1.0 ARM64 reaches all eleven CUDA workloads with the rebuilt
compiler. Process wall time is 128.725 seconds, with 2,026 successful compiler
invocations. The only reported CUDA errors are eleven error-701 resource-limit
rejections during launch-size tuning. It exits 255 when the network upload
fails (`console_upload_failed`), so no published score is available. See
`structurize-geekbench.json`. Compiler processes overlap; their aggregate time
is not application wall time. This single run does not establish an overall
speedup against the earlier runs, which also used different profiling settings.
