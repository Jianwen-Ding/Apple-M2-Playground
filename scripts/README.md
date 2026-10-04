# Shared probe tooling

`run.py` uses only Python's standard library and creates a unique directory
under `/scratch/apple-m2-playground/runs/` for every invocation:

```sh
python3 -B scripts/run.py env
python3 -B scripts/run.py check
python3 -B scripts/run.py drm-smoke --device /dev/dri/renderD128
python3 -B scripts/run.py params --device /dev/dri/renderD128
python3 -B scripts/run.py time --device /dev/dri/renderD128
```

Set `--scratch-root /some/path` to choose another output root. The `CC`
environment variable selects the compiler (for example, `CC=clang`).
The equivalent Make targets are `env`, `check`, `smoke`, `params`, and `time`.
`check` parses every `scripts/*.py` and syntax-checks every `tests/*.c` with
C11, `-Wall -Wextra -Werror -O2`, without opening DRM.

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

If a concurrent or future EGL/GLES probe is present while system SDK headers are
absent, supply an available SDK include root through the existing compiler override:

```sh
make check CC='cc -I/save/workspace/AGX_Probe/mesa/include'
```

This reads vendor headers without modifying them and still checks every C file.
Missing required headers cause FAIL; probes are not silently skipped.
