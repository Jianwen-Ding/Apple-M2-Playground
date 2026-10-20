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
make opcode-describe        # GPU: describe the 49 non-faulting undecoded opcodes (CONFIRM_GPU_FAULTS=1)
make verify-opcode-describe # Check retained opcode-description evidence offline
make sync-probe             # GPU: 0x18/0x78 barrier/wait and ending-opcode tests (CONFIRM_GPU_FAULTS=1)
make verify-sync-and-end    # Check retained sync/end evidence offline
make barrier-stress         # GPU: 0x68 vs 0x78 message-passing stress (CONFIRM_GPU_FAULTS=1)
make verify-barrier-stress  # Check retained barrier-stress evidence offline
make test-in-shader-clock   # GPU: read a CPU-written timer inside a shader
make verify-in-shader-clock # Check retained in-shader clock evidence offline
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
- [Remaining work, safe and unsafe](docs/remaining-work.md): every open Task 1 item split by GPU risk (2026-10-17)
- [ISA coverage](docs/isa-coverage.md): every applegpu instruction descriptor, its unaccounted bits and hardware status (regenerate with `python3 -B scripts/isa_coverage.py`)
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

### Offline simulator replay

`make replay-atomic-variants` executes all 74 retained atomic-variant programs in
the Rust simulator from the adjacent `AGX-Performance-Simulator` checkout
(override `SIMREPO`). Build that simulator with `make rust` first. No GPU is used.
Every deterministic output/table word is compared; contended float adds are
checked for a valid serialization using the independent rational float model.
Use `python3 scripts/replay_atomic_variants.py --only REGEX --run PATH` to narrow
a regression. This supplements `make verify-atomic-variants`, which independently
checks the retained hardware evidence and its source hashes.

`make replay-integer-atomic-suite` checks all 88 retained standard device and
threadgroup integer-atomic cases (44 each): return/non-return, distinct/shared
addresses and all established integer operations. Override `INTEGER_ATOMIC_SUITE`
for another local suite. This complements the separate 74 atomic-variant replays.

`make replay-geometry-suite` checks all eight retained standard 1-D/2-D/3-D
geometry cases, including non-warp-sized workgroups. Override `GEOMETRY_SUITE`
for another local suite. This is functional output replay, separate from the
placement-dependent SR20 evidence checked by `verify-sr-shape`.

`make verify-simulator-launch` checks malformed launch/resource inputs and mixed
batch isolation against the adjacent simulator's `agx_dispatch`. It uses a
synthetic stop-only shader, checks serial/parallel batch order and unchanged
valid controls, and requires no GPU or new hardware evidence.

`make verify-simulator-geometry` checks functional empty grids (all three axes),
partial workgroups and explicit writer-index capacity errors, with unchanged
mapped memory. These are synthetic input-domain checks, not hardware evidence.

`make replay-simulator-sr` compares all six retained divergence programs against
the functional simulator: 1,518 selector/pattern comparisons with lane values
and inactive writes checked. SR17/SR20 placement and time-varying SR113 remain
excluded from equality checks; this does not provide new hardware validation.

`make replay-simulator-cost-sr` checks 6,171 reconstructed SIMD-group probes:
retained divergent SR values, both width repetitions (including adjacent-register
preservation for odd/64-bit encodings), and SR18/19 resource sweeps. It preserves
lane identity via injective synthetic addresses, not aggregate value sets. Build
the adjacent simulator's `cost_special_registers` example first. This is value
replay, not execution of the original hardware shader or hardware timing.

`make replay-memory-suite` replays the simulator repository's retained device
loads, device stores and threadgroup layout cases (102 recordings as of
2026-10-17). Override `MEMORY_SUITE` to use another local suite directory.
Build the current simulator first: its `suite_check` now returns failure for
mismatches, unsupported cases or an empty selection, and rejects incomplete
deterministic expected buffers. These are offline replays, not new hardware runs.

`make replay-control-suite` checks all 23 retained control-flow cases: integer
and float conditions, uniform branches, lane-dependent trips and nested loops.
Override `CONTROL_SUITE` for a local evidence subset. The simulator's performance
tracer now shares lazy decoding across groups while keeping execution state
independent; this target uses the real-memory functional executor for exact
hardware-output replay, not the performance tracer's approximate memory model.

`make replay-cross-lane-suite` checks the simulator's retained SIMD/quad
reductions, scans, shuffles and quad ballots, both full and masked (130 cases as
of 2026-10-17). Override `CROSS_LANE_SUITE` for another local suite. This uses the
current checker's `--case-prefix` selection and fails if any family is absent.
The separate 16/64-bit width evidence remains checked by `make verify-cross-lane-width`.

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
atomic add was validated on the way. Imageblock layouts in the USC Shared word
identified **SR12/SR13** (imageblock width/height) and **SR15** (sample stride;
its old "constant" 16 is the default field 0): **33 of 256** are now identified.
Two custom helper-program attempts each stalled ~0.5 s and were stopped.

**Cross-lane width and scan order (2026-10-16).** From recorded hardware words (no new encodings):
16-bit `simd_*` / `quad_*` reductions and scans combine at 16 bits (fp16, denormals kept), and **64-bit sources are
read as their low 32 bits: there is no 64-bit warp reduction**. SIMD prefix scans are a 32-lane **Sklansky**
network. [Finding](novel-results/2026-10-16-cross-lane-width/README.md), `make verify-cross-lane-width`.

**Clock states on battery and a silent llvmpipe fallback (2026-10-16).** On battery, sustained load drops the GPU to
a clock ~2.1x slower, and short gaps keep it fast. Vulkan device 0 was briefly llvmpipe, with correct-looking results.
[Finding](novel-results/2026-10-16-battery-clock-states/README.md), `make verify-battery-clock-states`. Simulator
side: every SPIR-V workload re-timed with the two-timestamps-before pattern (AGX-Performance-Simulator
`results/2026-10-16-asahi-retime`).

**Special registers completed for compute (2026-10-16).** SR21 is the hardware **VM slot** (1..63, distinct
between live VMs, least-recently-used cycling). Under divergence only SR56-59 change (active rank / count in the quad and SIMD group).
SR16 = lane & 3, and SR60 / SR63 are constants. Every other selector reads 0. SR113 is a global firmware power-state bit: set on a 56 ms
cycle (7 x the 8 ms power-sample period) while the GPU is busy, and cleared after about 2 ms of idle. The finding includes a map of all 256 selectors with PTX equivalents:
[finding](novel-results/2026-10-16-special-registers/README.md), `make verify-special-registers`.

**Unsafe-probe session: atomics and loops (2026-10-17, owner-approved).** Encodings Mesa never emits now run only
after the same program with a known surrogate instruction passes `agx_run` (AGX-Performance-Simulator
`scripts/probe_variants.py`). Device-atomic bit 45 turns `sub` into a **float32 atomic add** with exactly PTX's
`atom.add.f32` semantics (nearest even, denormals flushed, atomic under contention) and `cmpxchg` into a **64-bit
unsigned min / max** (bit 46 = max; Rt returns a changed flag). Ops 11-15 end the issuing SIMD group. 54 dispatch
pairs, 0 faults: [finding](novel-results/2026-10-17-atomic-variants/README.md), `make verify-atomic-variants`. The
2026-10-12 `while_*` "hangs" were a non-terminating test loop plus dispatches sent during recovery; all 24 condition
codes now run bounded and match the simulator ([failed approaches](notes/failed-approaches.md)).

**Transcendentals against PTX (2026-10-16).** fp32 `exp2` reads x as Q.23 fixed point, truncated, with a
ones'-complement negative, then uses one 2^23-entry table: this model is exact on 637 M recorded inputs.
`sin_pt_2` is a table over |x| truncated to Q.23. `rcp`, `rsqrt`, `ex2` (exactly at its 2 ulp bound), `lg2` and
`sin` meet PTX's `.approx` bounds. **Mesa's cosine sequence does not (2^-20.29 against 2^-20.4)**; an fma-split range
reduction fixes it (2^-20.70). [Finding](novel-results/2026-10-16-transcendentals/README.md),
`make verify-transcendentals`.


**Uniform call/return decoded (2026-10-17).** Direct, register-indirect and nested
calls return through the buffer-relative byte link when the continuation executes
`pop_exec r0l, 2`. Partial/divergent behavior remains open.
[Finding](novel-results/2026-10-17-call-ret/README.md), `make verify-call-ret`.
Further [atomic control-bit probes](novel-results/2026-10-17-atomic-gap-bits/README.md)
record five matching add variants, bit-29 suppression on three operations and a
recovered bit-31 fault; `make verify-atomic-gap-bits`.

[Threadgroup atomic follow-up](novel-results/2026-10-17-tg-atomic-followup/README.md):
27 variants, no new faults/hangs. Opcodes 11–15 stop the issuing group even with
an empty mask; tested control-bit changes match the integer baseline.
`make verify-tg-atomic-followup` checks exact evidence and simulator gates.
The probe watchdog now retains memory-pressure and process diagnostics on a
timeout; `make test-probe-watchdog` tests its bounded failure paths without a GPU.

**Sparse-mask shuffles (2026-10-20).** Inactive lanes contribute index bits, so the generic four-shuffle lowering needs index initialization before divergence. Paired b32 lowerings preserve 64-bit payloads: 360,552 defined positive data words exact, 236 retained dispatches, zero faults. [Finding](novel-results/2026-10-20-shfl-mask/README.md), `make verify-shfl-mask`.

**Stop and return context (2026-10-20, owner-authorized unsafe probes).** Empty-mask stops preserve conditional-only mask depths, while the same reactivation pattern after return loses depth-1 lanes. Partial active stops leave masked lanes able to resume. 17 variants / 51 dispatches, zero faults; six simulator counterexamples retained explicitly. [Finding](novel-results/2026-10-20-empty-stop/README.md), `make verify-empty-stop`.

**Divergent return winner (2026-10-20).** With lane 0 excluded and active target operands disagreeing, the lowest active lane chooses the landing in every first-active position 1..31 and both address assignments. 64 variants / 192 dispatches, no faults. [Finding](novel-results/2026-10-20-ret-winner/README.md), `make verify-ret-winner`; simulator extension remains open.

**Indirect-call winner and links (2026-10-20).** The lowest active lane selects the target, only matching lanes enter, and r1 receives the link in **all issue-active lanes**, including non-entering lanes. Inactive lanes retain r1. 74 variants / 222 dispatches, no faults; a post-pop snapshot exposes the simulator's narrower link-write bug. [Finding](novel-results/2026-10-20-call-winner/README.md), `make verify-call-winner`.
