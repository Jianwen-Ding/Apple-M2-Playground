# Initial DRM baseline — 2026-10-04

Reproduce from the repository with `make smoke`. The retained run built the
C smoke test with `cc -std=c11 -Wall -Wextra -Werror -O2`, opened
`/dev/dri/renderD128`, and queried `DRM_IOCTL_VERSION` successfully.

```text
Driver: asahi
Version: 0.0.0
Description: Apple AGX Graphics
```

`environment.json` records the container/kernel, device nodes, tool availability,
header hashes, and repository state at execution. `summary.json` identifies
the source hashes and actual commands. The scratch paths in command logs are
historical; `make smoke` rebuilds into a new run directory.

Additional setup checks passed: `make env` and `make check`. A run targeting
`/dev/dri/nonexistent-probe-test` returned status 1 and preserved its failure
logs in scratch, verifying that a missing device is not reported as success.

Scope: DRM device access and ioctl communication only. No shader executed,
and no new ISA behavior, exact GPU identity, or timing property was established.
