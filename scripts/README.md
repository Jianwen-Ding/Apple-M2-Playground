# Shared probe tooling

`run.py` uses only Python's standard library. Baseline/DRM runs create a unique
directory under `/scratch/apple-m2-playground/runs/`; delegated compute runs
create a unique directory directly under the supplied scratch root:

```sh
python3 -B scripts/run.py env
python3 -B scripts/run.py check
python3 -B scripts/run.py drm-smoke --device /dev/dri/renderD128
python3 -B scripts/run.py params --device /dev/dri/renderD128
python3 -B scripts/run.py time --device /dev/dri/renderD128
python3 -B scripts/run.py compute --smoke --device /dev/dri/renderD128
```

Set `--scratch-root /some/path` to choose another output root. The `CC`
environment variable selects the compiler (for example, `CC=clang`).
The equivalent Make targets are `env`, `check`, `smoke`, `params`, `time`, and `compute`.
`check` parses every `scripts/*.py` and syntax-checks every `tests/*.c` with
C11, `-Wall -Wextra -Werror -O2`, without opening DRM. Source hashes are checked
again after compilation; concurrent additions/edits produce FAIL rather than
validating a different snapshot. In-progress probes may be syntax-checked,
but are not run by `check`.

`collect_environment.py` inventories the kernel/container, tool paths, DRM
node permissions, installed header hashes, and repository state. It does not
open the GPU. Missing optional tools/device-tree files are captured explicitly.

Runs preserve `environment.json`, `summary.json`, and per-command JSON and
stdout/stderr logs. Builds have a 60-second timeout, and the DRM version query
has a 10-second timeout. Recorded host elapsed time is diagnostic, not GPU
instruction timing. Build/probe failures return a nonzero process status.

Generated output belongs in scratch; scripts and selected evidence belong in
the repository. Future execution probes should use similarly explicit logs
and completion checks.

`run_params.py` also accepts `--repeats 1..10` (default 3). It records actual
compiler dependency hashes and header snapshots, requires successful probe
output on each repeat, and fails on differing outputs or changed dependencies.
See [parameter findings](../experiments/baseline/device-params.md).

`run_time.py` performs 8 warmup, 128 burst, and two 64-sample paced phases
(10 ms requested spacing), each with a 10-second bound. PASS requires every
phase command to succeed, exactly the requested number of successful JSON
samples, matching metadata, sequential indices, valid host brackets, positive
elapsed time, and no backward returned timestamps. Equal steps are recorded;
PASS is not a statistical rate criterion. Empty, malformed, truncated, or failed
records produce a failed summary and nonzero status. Timeout logs preserve
available partial stdout/stderr. See [time findings](../experiments/timing/driver-time.md).

`PROBE_INCLUDE` supplies the EGL/GLES/Vulkan header root, defaulting to the
unchanged Mesa checkout at `/save/workspace/AGX_Probe/mesa/include`. Override
with a different SDK root, or pass `--include-dir` to the shared runner:

```sh
make check PROBE_INCLUDE=/path/to/sdk/include CC=cc
python3 -B scripts/run.py check --include-dir /path/to/sdk/include
```

`CC` supports compiler arguments/wrappers through shell-style splitting and
is exported by Make. Missing required headers cause FAIL; C files are not skipped.
Using checkout headers does not identify the installed runtime implementation.

`make compute` runs the P2 smoke subset: one initialization-only control,
constant count 32, index count 33, wrong-oracle rejection, invalid GLSL rejection,
wrong-node rejection, and a final initialization-only control. Every readback
includes main payload, guards/padding, and an untouched 16-word control buffer.
It performs two dispatches and verifies bytes with the independent Python oracle.

The full original P2 matrix (22 dispatches, four readback controls) remains
available through `python3 -B scripts/run_compute.py` or shared `run.py compute`
without `--smoke`. The standalone runner uses `PROBE_INCLUDE` or `--mesa-include`,
honors `CC`, and defaults to `/scratch/apple-m2-playground/compute-runs/`.
Builds have a 30-second limit; API children have a 15-second timeout with process-
group termination. Fence waits have a five-second deadline. Both modes stop
on unexpected failure; they claim compute/readback, not raw ISA or GPU timing.
See [P2 report](../experiments/baseline/compute-readback.md).

`make instruction-candidates` is offline only. It exports six ALU immediate edits,
changed bits and uint32 mathematical fixtures to
`SCRATCH_ROOT/agx-instruction-candidates.json`. `APPLEGPU_ROOT` and `MESA_ROOT`
select reference checkouts, independently of SDK headers/`PROBE_INCLUDE`.
The script also accepts those roots explicitly and supports distinct r0..r31
registers. It checks assembler/decoder agreement with a restricted source-bitfield
transcription; it does not patch, import or execute a shader.
[Candidate evidence](../results/2026-10-04-agx-instruction-candidates/README.md)
records the tested scope.

Completed standalone `run_vulkan_caps.py` and `run_gles_time.py` retain their
[capability](../experiments/baseline/vulkan-runtime.md) and
[failed calibration](../experiments/timing/gles-timer-calibration.md) evidence.
Their syntax/evidence was reviewed here; no capability or timer GPU rerun occurred.
The subsequent instruction integration adds the completed pinned execution path
below.

`make agx-instruction` runs the recorded Vulkan baseline plus the pinned move-
immediate variation: ten unchanged baseline dispatches, four instruction/control
dispatches and one no-dispatch readback. It requires the existing isolated runtime
under `SCRATCH_ROOT/vulkan-runtime/usr/lib64`, uses `CC`, `PROBE_INCLUDE` and the
`MESA_ROOT` SPIR-V grammar, and creates unique output under the standalone runner's
scratch root. It downloads/installs nothing. `run_vulkan_compute.py --output`,
`--runtime`, `--include`, `--grammar` and `--cc` allow explicit paths.

The patcher accepts only the exact constant blob/decoder hashes, walks the main
instruction boundary, changes immediate bit 16, and refreshes the actual Mesa
25.3.6 SHA1 wrapper. It suppresses vendor bytecode writes and emits patch artifacts
without GPU access. Hardware reproduction requires `--probe-mov`; import failure,
completion failure or any whole-buffer mismatch stops the suite. See
[execution scope](../experiments/arithmetic/first-agx-instruction.md).

`make agx-imadd` runs a separate index-shader suite using `run_agx_imadd.py`
and `patch_agx_imadd.py`: five dispatches, one no-dispatch readback, unchanged
before/after controls, patched counts 33/257, stale-digest and wrong-node rejection.
It pins the index blob and changes only immediate addend bit 40. Paths and bounds
match the existing Vulkan suite. `make verify-imadd` runs offline rejection tests
and independent checks on the committed hex evidence; it performs no GPU calls.
See [multiply-add scope](../experiments/arithmetic/imadd-addend.md).

Special-register probes use `patch_agx_sr.py` to reconstruct pinned single-read,
paired-read, and sparse-mask native shaders. `run_agx_sr_scan.py` serializes bounded
hardware cases and guard checks; `characterize_agx_sr.py` varies prefix counts.
`run_agx_sr_context.py` uses twelve dispatches in one logical device. Use each
runner's `--help` for selector/count options. `verify_sr_evidence.py` independently
reconstructs shader bytes and buffers with the Python standard library;
`verify_sr_findings.py` checks the retained lane/context observations. Run
`make verify-sr` without GPU access.

## Opcode descriptions (2026-10-11)

* `run_drm_opcode_describe.py`: length/register, granularity and timing suites for the 49
  non-faulting undecoded opcodes (`--dry-run` builds and checks every body offline;
  `--names REGEX --repeat N` reruns selected jobs). It refuses the faulting opcodes.
* `analyze_opcode_describe.py RECORD [--jobs]`: summary against the reference-body oracle.
* `verify_opcode_describe.py`: offline checks of `results/2026-10-11-opcode-describe/`.

