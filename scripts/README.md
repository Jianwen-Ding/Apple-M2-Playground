# Shared probe tooling

`run.py` uses only Python's standard library and creates a unique directory
under `/scratch/apple-m2-playground/runs/` for every invocation:

```sh
python3 -B scripts/run.py env
python3 -B scripts/run.py check
python3 -B scripts/run.py drm-smoke --device /dev/dri/renderD128
```

Set `--scratch-root /some/path` to choose another output root. The `CC`
environment variable selects the compiler (for example, `CC=clang`).
The equivalent Make targets are `env`, `check`, and `smoke`.

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
