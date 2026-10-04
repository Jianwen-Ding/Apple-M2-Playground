# Offline development environment

Offline work can compile the C probes, check Python syntax, inspect AGX binary
encodings, and compare model behavior without opening a GPU device. A successful
offline check is not a hardware observation.

Run `make check` for Python/C syntax checks, or `make env` for environment
inventory. Neither command opens a DRM device. Offline AGX model/encoding
checks remain a follow-up item.

For the C probe, a Linux compiler and DRM UAPI headers are still required.
The existing applegpu tools are supplied outside this repository in
`../AGX_Probe/applegpu/`. If absent in a later session, obtain them from
[upstream](https://github.com/dougallj/applegpu) and record their revision.

The applegpu assembler, disassembler, and model can be studied offline. Its
`hwtestbed` builds with `xcrun` and links Metal; it is not the Linux execution
backend. Do not run its hardware tests here expecting a DRM path.

Future offline fixtures should include exact byte strings and independently
specified expected outputs, with their source and applicable GPU generation.
