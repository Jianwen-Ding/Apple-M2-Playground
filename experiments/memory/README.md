# Memory probes

Questions: address and offset calculation, access widths, alignment, visibility
after waits, workgroup memory, and atomic ordering.

Begin with a small initialized buffer and known valid addresses. Vary one
offset or width and retain the complete expected/observed buffer. Separate CPU
mapping and coherency behavior from shader load/store semantics. Cross-thread
tests require a verified launch layout and completion primitive.

First dependencies: verified device parameters, buffer lifecycle, constant-write
submission, and exact readback.

[Device-load latency](load-latency.md) (2026-10-10): pointer-chase curve from 2 KiB to
256 MiB, a page-stride TLB check, and cycle figures.
