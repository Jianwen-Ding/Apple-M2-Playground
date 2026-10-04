# Vulkan runtime capability evidence — 2026-10-04

See [the report](../../experiments/baseline/vulkan-runtime.md) and run
`python3 scripts/run_vulkan_caps.py --setup` from the canonical repository.
Only the matching signed Fedora runtime RPM is extracted in scratch; no
system driver or global runtime configuration is modified.

| Run | Result |
| --- | --- |
| `missing-runtime` | Expected failure: instance -9, missing libdisplay-info.so.2 |
| `repaired-first` | Capability enumeration passed |
| `repaired-repeat` | Capability enumeration passed |
| `missing-runtime-repeat` | Expected failure: instance -9, missing dependency |
| `final-setup` | Signature verification, extraction and capability enumeration passed; final runner |
| `final-repeat` | Identical capabilities/hashes; final runner |
| `final-missing` | Expected failure without LD_LIBRARY_PATH; final runner |

Each directory contains `record.json` (commands, return codes, stdout/stderr,
capabilities, overrides and hashes), `stdout.json` (raw probe JSON), and
`loader.stderr.txt`. Early records predate the addition of RPM verification,
ELF packaging notes and command elapsed times; final records contain these.
[verification.json](verification.json) records syntax/compile checks, repeat
comparisons and the persistent global missing dependency.

Probe sources belong in `tests/vulkan_caps.c` and `scripts/run_vulkan_caps.py`.
Binaries, downloaded RPMs, extracted libraries and scratch setup manifest are
regenerable artifacts under `/scratch/apple-m2-playground/vulkan-runtime/`.
The `downloads` folder retains the initial unused unsigned Koji RPM and the
signed Fedora archive RPM. No shader or shader binary was generated.

The real library reports Mesa 25.3.6, despite registered 25.1.9 package
metadata. `rpm -V` and ELF notes in final records preserve that discrepancy.
Memory size and all feature/limit fields are driver reports, not independent
hardware execution measurements. ShaderFloat64 is unsupported; shader-object
binary export/import has not been tested. The records establish capability
queries on the Asahi render node only.
