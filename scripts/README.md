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
