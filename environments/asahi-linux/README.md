# Asahi Linux hardware environment

## Requirements

- Linux with the Asahi DRM driver and access to its render node.
- A C11 compiler, Linux DRM UAPI headers, Python 3, and optionally Make.
- No libdrm dependency for the initial version-query smoke test.

The current environment is a Fedora 42 container sharing an Asahi aarch64
kernel. `/dev/dri/renderD128` responds as `asahi`, described as
`Apple AGX Graphics`. Device-tree model files are not exposed here, so the
project's M2 Max specification has not yet been independently verified.

## Current boundary

Opening the node and querying the driver works. GPU compute submission,
buffer readback, and instruction replacement still need implementation.
Installed `asahi_drm.h` includes device parameters and a time-query interface;
these have not been exercised yet.

Keep binaries and run directories under `/scratch/apple-m2-playground/`.
An optional explicit device path lets the same smoke test run if node numbering
changes. Kernel permissions or container device exposure can affect access.

See [the smoke-test instructions](../../tests/README.md) for the current
manual build/run command. Shared runner commands will be added with the tooling.
