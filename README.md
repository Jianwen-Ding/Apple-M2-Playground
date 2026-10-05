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
