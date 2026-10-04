# Independent review — 2026-10-04

Accepted as driver capability evidence only. Independently parsed raw JSON,
compared final setup/repeat capabilities and provenance hashes, checked successful
probe exit codes, and verified the retained manifests before changing anything.
The missing-runtime control remains instance result -9. No compute, binary import
or ISA semantics claim follows from these queries.

Corrections: honor shell-tokenized `CC` and `--mesa-include`; capture the exact
source used for future builds; query driver properties only for Vulkan 1.2+
or advertised `VK_KHR_driver_properties`; reject pre-1.1 physical devices;
retain launch errors and kill the process group on timeout with bounded output
collection. Existing actual device/API/extension responses supported the original
query; the conditional fixes handling of alternative devices. See Khronos'
[driver properties definition](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceDriverProperties.html).

One capability rerun with `CC='cc -pipe'` and an explicit include root passed;
[review-run/record.json](review-run/record.json) has identical capabilities to
`final-repeat`, current hashes, captured sources and commands. The standalone
C probe built with strict warnings. No package download or re-extraction was needed.
[review-timeout-control.json](review-timeout-control.json) exercises the actual
revised helper against a sleeping CPU process at 50 ms; partial stdout survived
and the process was killed. No GPU timeout was induced.

Pinned signed RPM/digest and installed binary discrepancy remain documented.
The download has a socket inactivity timeout and size cap, not a whole-download
wall-clock deadline. This review did not repeat network setup. A hostile peer
trickling bytes could exceed 30 s; use an external process deadline if setup needs
a strict total bound. Extraction is for a pinned signed package, not a general RPM
installer. No vendor changes, commits, pushes, or shared-file edits were made.

Next: separately validate logical-device compute and shader binary roundtrip;
retain stack-specific provenance and distinguish those observations from advertised
capabilities. The compute agent owns that work.
