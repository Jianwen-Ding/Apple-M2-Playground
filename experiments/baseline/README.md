# Baseline probes

| Control | Reviewed status |
| --- | --- |
| DRM access | `make smoke`; Asahi render-node open/version query passed |
| Device identity/topology | `make params`; [P1](device-params.md) reports G14C and 38 enabled mask bits |
| Linux execution path | [Backend inventory](linux-compute-backend.md); historical EGL/Vulkan capability and source evidence |
| Submission/readback | `make compute`; [P2](compute-readback.md) passed Mesa GLES compute with exact payload/guard/control bytes |

P2 includes GLES buffer allocation, initialization, completion and host mapping.
A standalone direct-UAPI memory/submission backend remains separate future work.
The submission/readback case is the control for later ISA experiments. Preserve
shader source, emitted-code provenance when available, compiler/runtime hashes,
command setup and whole-buffer oracles. GLSL execution does not establish a
known native AGX sequence or raw instruction replacement.
