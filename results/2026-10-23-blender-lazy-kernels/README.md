# Blender Cycles kernel loading through ZLUDA

M2 Max, Asahi Linux, 2026-10-23. Blender 5.1.0 ARM64 ran headless with its
bundled `kernel_compute_75.ptx.zst`; the bundled cubins were temporarily
hidden in the scratch extraction. These are development probes, with the
ZLUDA compilation cache disabled. There is no completed render or Metal
comparison in this report.

ZLUDA's new opt-in `ZLUDA_AGX_LAZY_KERNELS=1` path compiles one PTX entry in
`cuModuleLoadData` and compiles another when `cuModuleGetFunction` asks for it.
Each entry uses the same global-data layout and buffer. A two-kernel driver
test compiled both images, compared their global layouts, exercised lookup
and unload, and passed. This path is disabled in checked mode and for ELF
objects.

The serial headless run loaded the initial Cycles module in about 12 seconds.
It spent a cumulative 122 seconds in the first seven `cuModuleGetFunction`
calls and then waited on `kernel_gpu_integrator_shade_background`. The probe
was stopped while that compiler was still active. The driver implemented
`cuOccupancyMaxPotentialBlockSize` during this run; Blender accepted its
recommendations and advanced past the earlier unsupported-call error.

The separate offline `llc` probe compiled the optimized LLVM IR with only
`kernel_gpu_integrator_reset` in 7.1 seconds. With only
`kernel_gpu_integrator_shade_surface`, it exceeded a 180-second timeout.
This identifies a large per-kernel compiler cost that lazy loading alone does
not remove. Both probes used `-agx-experimental-leaf-calls`; the headless
Blender run used the existing ZLUDA compiler binary without that option.

ZLUDA also has an opt-in `ZLUDA_AGX_PARALLEL_KERNELS=N` mode (up to 16)
that starts background compilation of the other PTX entries after module
load, so sequential kernel registration can overlap independent compiler
processes. With four workers and the cache disabled, Blender's module load
again took about 12 seconds. Its first requested kernel took 14.0 seconds;
the next three were ready or within 0.7 seconds, and the later subsurface
kernel waited 23.3 seconds. The run still reached only seven kernel lookups
before its 240-second timeout: `kernel_gpu_integrator_shade_background` had
not finished compiling. One `zoc` worker reached about 12 GiB resident memory,
and four workers together exceeded 20 GiB. Parallel compilation reduced
some lookup waits but did not remove the longest-kernel bottleneck.

Bounded LLVM stage probes on the optimized, surface-only IR reached the
AGX always-inline pass in 2.0 seconds and the AGX codegen-preparation pass in
18.3 seconds. The code reached the point immediately before LLVM's
`structurizecfg` in 26.7 seconds and finished that pass in 93.1 seconds. It
did not reach instruction selection within 30 seconds or finish instruction
selection within 60 seconds; those smaller timeouts are consistent with the
93-second structurization result. The inliner left a single surface kernel
of about 354,000 IR lines and 22,500 basic blocks, so control-flow
structurization has a very large input. This makes support for deeper direct
calls, without forcing the entire device call tree into one kernel, a
concrete compile-time priority. No production speedup is established yet.

## Dead device-function code generation

Under the opt-in AGX call path, the backend's inliner left 35 unreferenced
device functions behind after it expanded their callers. The backend still
generated machine code for them. Adding LLVM GlobalDCE immediately after the
inliner reduced the camera-only module from 36 emitted function definitions
to its one kernel. On the exact optimized camera IR, standalone
`llc -filetype=obj` fell from 6.729 to 0.484 seconds (13.9× faster), and the
relocatable object fell from 4,441,944 to 52,016 bytes. The camera kernel's
44,222 machine-code bytes were identical between the two objects (SHA-256
`48252ea19c0650f3a52e3011fa461e42f44df469d7d5964a8eabb9fa17c694ba`).
The standalone `llc` comparison is a backend result on one kernel, not a
Blender render. The AGX codegen suite and simulator call fixtures passed
after the change.

The full `zoc` command on the same extracted camera-only PTX, with
`ZLUDA_AGX_LLVM_ARGS=-agx-experimental-leaf-calls`, took 24.18 and 24.35
seconds with the previous backend and 11.96 seconds with GlobalDCE (about
2.0× faster). Both builds produced byte-identical optimized LLVM IR. This
comparison includes PTX translation, LLVM optimization, machine-code
generation, and writing the object; it still covers one selected Cycles
kernel rather than the whole Blender render.

The AGX Performance Simulator retains its physical occupancy estimate for
throughput waves and now exposes a separate B5 co-residency bound matching
the runtime's launch recommendation. Neither model has been calibrated for
the compile-time probes or a Blender render.
