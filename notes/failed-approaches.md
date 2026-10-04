# Failed approaches and known limitations

| Date | Approach or check | Actual observation | Next action |
| --- | --- | --- | --- |
| 2026-10-04 | Discover libdrm through `pkg-config --modversion libdrm` | Package metadata was unavailable | Initial smoke test uses installed DRM headers and direct ioctl calls |
| 2026-10-04 | Reuse supplied applegpu hardware harness on Linux | Inspection found `xcrun` and Metal framework dependencies; execution was not attempted | Build a separate Linux/DRM execution backend; reuse offline tools as appropriate |
| 2026-10-04 | Identify board through `/proc/device-tree/model` and `compatible` | Both paths absent in the container | [Parameters now report G14C](../experiments/baseline/device-params.md); exact board and memory capacity remain unmeasured |
| 2026-10-04 | Discover Vulkan/OpenCL tooling on `PATH` | `vulkaninfo`, `clinfo`, `glslangValidator`, and `spirv-as` were not found | Inventory libraries before choosing a compute backend; tool absence alone does not prove API absence |

The DRM version smoke test has passed. No failed GPU shader submissions or
instruction probes have been observed yet. Add such failures with their inputs,
return codes, logs, and control result when they occur.

## Reviewed read-only probe failures

[Params evidence](../results/2026-10-04-device-params/README.md) retains missing
node (`ENOENT`), `/dev/null` version rejection (`ENOTTY`), wrong driver `apple`,
missing compiler, and invalid usage. The integration rerun repeated a missing
node failure. No unsupported GET_PARAMS or malformed kernel response was induced.

[Time evidence](../results/2026-10-04-driver-time/README.md) retains a missing
node and invalid argument bounds. Integration repeated `/dev/null` rejection
before GET_TIME. No unsupported GET_TIME, reset, or GPU submission was attempted.

Review found that the original time runner could accept zero or too few samples
and could crash on malformed JSON without a summary. The corrected runner
requires exact successful counts and validates metadata/sample fields before
analysis. [Synthetic regression evidence](../results/2026-10-04-driver-time/integration-review/verification.json)
shows malformed/empty/truncated data, failed records, invalid types, duplicate
indices, nonzero flags, invalid host brackets, backward time, and stalled time
all produce status 1 with `passed: false`. These are software failure injections,
not observed hardware faults. Available timeout output is retained; timeout and
permission failure paths were not induced in this review.

During final integration, another owner added a GLES C probe. The expanded default
`make check` failed on missing system `EGL/egl.h`. Supplying the unchanged Mesa
header include root via `CC='cc -I/save/workspace/AGX_Probe/mesa/include'` let all
four current C files pass syntax checking. The concurrent probe remains outside
this commit; no shader execution was performed by this integration review.
