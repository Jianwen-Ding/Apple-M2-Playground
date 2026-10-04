# Failed approaches and known limitations

| Date | Approach or check | Actual observation | Next action |
| --- | --- | --- | --- |
| 2026-10-04 | Discover libdrm through `pkg-config --modversion libdrm` | Package metadata was unavailable | Initial smoke test uses installed DRM headers and direct ioctl calls |
| 2026-10-04 | Reuse supplied applegpu hardware harness on Linux | Inspection found `xcrun` and Metal framework dependencies; execution was not attempted | Build a separate Linux/DRM execution backend; reuse offline tools as appropriate |
| 2026-10-04 | Identify board through `/proc/device-tree/model` and `compatible` | Both paths absent in the container | Query Asahi parameters; retain the user-supplied target as unverified metadata |
| 2026-10-04 | Discover Vulkan/OpenCL tooling on `PATH` | `vulkaninfo`, `clinfo`, `glslangValidator`, and `spirv-as` were not found | Inventory libraries before choosing a compute backend; tool absence alone does not prove API absence |

The DRM version smoke test has passed. No failed GPU shader submissions or
instruction probes have been observed yet. Add such failures with their inputs,
return codes, logs, and control result when they occur.
