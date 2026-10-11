# Apple M2 Playground

Task 1 workspace for probing Apple AGX on Asahi Linux. The project target is an
M2 Max with 64 GB of unified memory, as supplied by the project owner. The
current container exposes Asahi driver parameters for G14C revision `0x11`,
chip `0x6021`, with 38 enabled cores derived from its masks. Local Mesa naming
logic interprets this as M2 Max; the 64 GB capacity has not been measured.

The goal is reproducible hardware observations that can guide PTX translation
and an AGX compiler backend. Device parameters, driver time, and Mesa-compiled
GLES compute with exact readback establish the baseline. A pinned native AGX
move-immediate bit edit now executes on G14C B1 with exact guarded readback.
This confirms that existing field interpretation in one shader; broader ISA
semantics, shader counters and instruction timing remain unvalidated.

## Layout

| Folder | Contents |
| --- | --- |
| `docs/` | Probe roadmap, measurement method, and source references |
| `environments/` | Requirements and setup for Linux hardware and offline work |
| `experiments/` | Plans and future runnable probes grouped by subject |
| `tests/` | Reusable smoke tests and regressions for confirmed behavior |
| `scripts/` | Environment capture and repeatable probe runners |
| `notes/` | Session notes, limitations, and failed approaches |
| `results/` | Selected environment snapshots and raw evidence worth keeping |
| `novel-results/` | New hardware findings, each paired with a reproducer |
| `templates/` | Experiment and finding report templates |

Source, notes, and selected evidence belong in Git. Regenerable binaries and
bulk run output belong in `/scratch/apple-m2-playground/`, which persists
across sessions but has no version control.

## Starting points

From this repository:

```sh
make env     # Record available tools, device nodes, kernel, and header hashes
make check   # Python/C syntax checks; no GPU device access
make smoke   # Build and run the DRM driver-access test
make params  # Three read-only Asahi identity/topology queries
make time    # 264 bounded driver timestamp queries; no shader execution
make compute # Two GLES dispatches, guards/control readback and negative checks
make instruction-candidates # Export offline ALU byte changes and uint32 oracles
make agx-instruction # Reproduce the pinned G14C move-immediate hardware suite
make agx-imadd # Reproduce the pinned G14C integer multiply-add addend suite
make verify-imadd # Check retained multiply-add evidence offline
make sr-shape    # SR reads across nine 1-D..3-D workgroup shapes
make sr-core     # 2048-workgroup SR20 core-id / constant check
make verify-sr-shape # Check retained shape/core/bit-15 evidence offline
make sr-meta     # SR18/SR19 vs single driver-metadata field edits
make verify-sr-resources # Check retained resource/width evidence offline
make timestamps  # Vulkan timestamp-placement hardware regression
make verify-timestamps # Check timestamp, fetch-cost and direct-DRM evidence offline
make drm-compute # Direct DRM dispatches: no Mesa or Vulkan in the path
make agx-loop-test # Loop emulator gate + small hardware loops
make verify-loops  # Check loop latency/throughput evidence offline
make verify-memory # Check pointer-chase load-latency evidence offline
make verify-sr-direct # Check direct-DRM differential SR scan evidence offline
make gpu-faults  # Summarize GPU timeouts/faults in a kernel log (LOG=...)
```

Run records and binaries go to scratch. Baseline/DRM runs use
`/scratch/apple-m2-playground/runs/`; shared compute creates a unique directory
under `SCRATCH_ROOT`.
Override with `make smoke DEVICE=/dev/dri/renderD128 SCRATCH_ROOT=/scratch/other`.
`PROBE_INCLUDE` selects the EGL/GLES/Vulkan header root (default
`/save/workspace/AGX_Probe/mesa/include`); `CC` selects the compiler. Vendor
headers are read without modifying vendor sources. Python-only equivalents
are documented in [scripts/README.md](scripts/README.md).

- [Probe plan](docs/probe-plan.md)
- [Asahi Linux environment](environments/asahi-linux/README.md)
- [Offline environment](environments/offline/README.md)
- [DRM probe tests](tests/README.md)
- [Device parameters and evidence](experiments/baseline/device-params.md)
- [First G14C native move-immediate observation](experiments/arithmetic/first-agx-instruction.md)
- [G14C multiply-add immediate addend observation](experiments/arithmetic/imadd-addend.md)
- [Vulkan unchanged binary roundtrip](experiments/baseline/vulkan-binary-roundtrip.md)
- [Independent native instruction placement review](experiments/arithmetic/native-control-disassembly.md)
- [Offline AGX integer candidates](experiments/arithmetic/agx-instruction-candidates.md)
- [Vulkan runtime/capability evidence](experiments/baseline/vulkan-runtime.md)
- [Failed GLES elapsed calibration](experiments/timing/gles-timer-calibration.md)
- [Compute/readback and evidence](experiments/baseline/compute-readback.md)
- [Linux backend reconnaissance](experiments/baseline/linux-compute-backend.md)
- [Shader-counter evidence gap](experiments/timing/shader-counter-candidates.md)
- [Driver time and evidence](experiments/timing/driver-time.md)
- [Reviewed progress and next tasks](notes/2026-10-04-probe-progress.md)
- [SR geometry, core id, bit-15 form](experiments/registers/sr-geometry-core-alt.md)
- [SR18/SR19 resources and get_sr widths](experiments/registers/sr-resources-width.md)
- [Command timestamps and fetch-bound code](experiments/timing/command-timestamps.md)
- [Direct DRM compute (no Mesa)](experiments/baseline/direct-drm-compute.md)
- [Counted loops and ALU timing](experiments/control-flow/loops-and-alu-timing.md)
- [Device-load latency](experiments/memory/load-latency.md)
- [Direct-DRM differential SR scan](experiments/registers/sr-direct-drm.md)
- [Opcode-scan kernel log](results/2026-10-10-opcode-scan-kernel-log/README.md)
- [Known limitations and failed approaches](notes/failed-approaches.md)
- [Timing investigation](experiments/timing/README.md)

Every report should distinguish a planned hypothesis, a software-model result,
an observed hardware result, and a confirmed finding. A successful DRM version
query proves device access; it does not prove shader execution.

The initial `test.txt` is the repository push smoke-test artifact.

Current priority is **actual AGX instruction execution**. The first pinned
move-immediate experiment passed: toggling immediate bit 0 changed active uint32
results from `0x12345678` to `0x12345679` at counts 33 and 257, preserving guards,
padding and the untouched tail. Unchanged controls and stale-integrity rejection
also passed. [Evidence and limits](novel-results/2026-10-04-first-agx-instruction/README.md)
keep this distinct from a novel architecture discovery. The index `imadd` addend
site has now also passed a separate 0-to-1 hardware test at counts 33 and 257,
with unchanged before/after controls and all 800 words across six buffers checked.
See the [scoped result](experiments/arithmetic/imadd-addend.md); general arithmetic
and instruction timing remain uncharacterized.

The [special-register hardware scan](experiments/registers/special-register-scan.md)
covered all 256 selectors with single and paired reads. No progressing timing
register was found through the tested 32-bit read path. Prefix and sparse masks
identified SR16 lane position, SR57 four-lane active population, and SR59
32-lane active population. `make verify-sr` checks retained evidence offline;
`make sr-scan` and `make sr-pairs` reproduce the full hardware sweeps.

The [geometry/core-id follow-up](experiments/registers/sr-geometry-core-alt.md)
ran nine local/group shapes (1-D to 3-D) and a 2048-workgroup dispatch. It
confirmed the geometry SRs needed for CUDA `threadIdx`/`blockIdx`/`blockDim`/`%laneid`,
found SR7 = SIMD groups per threadgroup, and showed SR20 = `(cluster<<4)|core`
over exactly the 38 driver-enabled cores (a `%smid` source). The bit-15 `get_sr`
form wrote nothing observable for all 256 selectors. `make verify-sr-shape` checks it offline.
A [resource follow-up](experiments/registers/sr-resources-width.md) identified SR18 as
threadgroup-memory bytes and SR19 as register allocation, by editing single driver
metadata fields on unchanged code. It also showed `get_sr` is 32-bit only
(`make verify-sr-resources`).

**Direct DRM path (2026-10-10).** `tests/drm_compute.c` now submits compute work
with raw Asahi ioctls: its own VM, BOs, USC pipeline words and CDM control stream,
with no Mesa or Vulkan. It reproduces the Vulkan results exactly (oracles, and
chain slopes within 1%), and it exposes firmware start/end timestamps per command:
an empty command is ~5.7 µs. New probes should prefer this path. See the
[report](experiments/baseline/direct-drm-compute.md).

**Timing (2026-10-10).** [Command timestamps](experiments/timing/command-timestamps.md)
are 24 MHz ticks. Honeykrisp attaches a compute timestamp to the end of the
current stream, so `Write; Dispatch; Write` measures nothing; record two before.
Unrolled code is fetch bound at ~1.84 ns/byte per instruction, independent of
dependencies and lane count. The GPU runs in two clock states ~1.65× apart, so
warm up before benchmarking. No shader-readable clock is known; dispatch-level
timing works.

**Loops and ALU timing (2026-10-10).** [Counted loops](experiments/control-flow/loops-and-alu-timing.md)
now run on hardware (`push_exec` / `while_icmp` / `jmp_exec_any` / `pop_exec`), gated
by an emulator check. Per SIMD group, dependent `iadd`/`fadd32` cost 2 cycles and
independent ones 1 cycle (at 1,398 MHz). A taken loop iteration costs ~38 cycles.
A core saturates at ~3.6 SIMD groups' worth of issue, and the GPU sustained 83% of
its non-FMA fp32 peak. The clock ladder spans 3.16×.

**Load latency (2026-10-10).** [Pointer chasing](experiments/memory/load-latency.md)
with `device_load` + `wait` gives ~50 cycles for ≤ 8 KiB (first level ends between
8 and 12 KiB), ~125–135 cycles for 12–64 KiB, and a flat ~349 ns for 1–32 MiB,
rising to ~388 ns at 256 MiB. The TLB adds at most ~32 ns. Every one of 13.2 M hops
matched its host oracle. A SIMD group keeps ≥ 16 loads in flight, and grid-stride
streaming reaches ~350 GB/s (≈ 89% of the advertised 400 GB/s) from 8 SIMD groups
per core.

**Special registers, direct DRM (2026-10-11).** A [one-dispatch 256-selector scan](experiments/registers/sr-direct-drm.md)
over launch parameters Vulkan never exposed identified **SR17** as the per-core
hardware SIMD-group slot (it equals SR53 only under light load; a `%warpid`
analogue) and **SR32** as the USC offset of the dispatch's pipeline words. SR113
is random. It also showed the preshader word must end the USC pipeline words.
30 of 256 selectors are now identified in compute. Reading registers from inside
the preshader showed the preamble runs **once per core per dispatch** with one
lane, in slot 96, with SR24 = 5 (main: 2); its uniforms are per core. A device
atomic add was validated on the way.
