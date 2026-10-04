# DRM and compute probes

`drm_smoke.c` opens a DRM render node and calls `DRM_IOCTL_VERSION` using
the installed Linux UAPI headers. It requires a C compiler, but not libdrm.
This checks device access and ioctl communication; it does not execute GPU code.

The shared runner builds in scratch and records environment, commands, output,
and exit status:

```sh
make check
make smoke
```

Manual build and run from scratch:

```sh
cp /save/workspace/apple-documentation-playground/tests/drm_smoke.c /scratch/drm_smoke.c
cd /scratch
cc -std=c11 -Wall -Wextra -Werror -O2 drm_smoke.c -o drm_smoke
./drm_smoke
```

An optional device path may be passed as the first argument.
Failures return a nonzero exit code and print the system error.

API reference: https://github.com/torvalds/linux/blob/master/include/uapi/drm/drm.h

## Asahi parameters and driver time

`drm_params.c` requires the installed `<drm/asahi_drm.h>`. It checks the
Asahi driver name, queries group 0, preserves raw bytes, and validates returned
size and topology before counting enabled mask bits. `drm_time.c` checks the
driver and reads GET_TIME with zero flags, bracketing each query with
CLOCK_MONOTONIC_RAW. Its arguments are `DEVICE SAMPLES(2..256) INTERVAL_MS(0..20)`.
Both return nonzero on failure; neither allocates or submits GPU work.

```sh
make params
make time
make check  # Parse every scripts/*.py and syntax-check every tests/*.c
```

Reports: [device parameters](../experiments/baseline/device-params.md) and
[driver time](../experiments/timing/driver-time.md). Host ioctl brackets do not
measure instruction latency. The time runner requires exactly 8/128/64/64
successful samples across its four phases and validates record structure,
indices, units, and host brackets before calculating rates.

Synthetic runner failure checks can be reproduced without opening DRM:

```sh
python3 -B results/2026-10-04-driver-time/integration-review/verify_runner.py
```

## Mesa GLES compute/readback

`gles_compute.c` loads EGL/GL entry points dynamically, requires the requested
EGL-associated Asahi render node and `Apple M2 Max (G14C B1)` renderer, and
compiles GLSL ES 3.20 compute. It bounds fence waits and preserves whole-buffer
bytes; the Python runner independently checks payload, guards, padding, and
an untouched second buffer. Direct C status alone is not an oracle PASS.

```sh
make compute  # Two dispatches, two readback controls, three negative checks
make check    # All tests/*.c and scripts/*.py; no device access
```

`PROBE_INCLUDE` selects the EGL/GLES/Vulkan header root, defaulting to
`/save/workspace/AGX_Probe/mesa/include`; `CC` chooses the compiler. No vendor
source modification is needed. [P2 report](../experiments/baseline/compute-readback.md)
links raw bytes and independent verification. The full matrix is available
through `python3 -B scripts/run_compute.py`.

Concurrent Vulkan/timer probes may be present. The shared check only parses or
syntax-checks them; execution and review belong to their respective owners.

## Pinned native AGX instruction delivery

`vulkan_compute.c` creates shader objects from validated SPIR-V or opaque binary
imports, checks the exact Asahi identity/UUID, and verifies bounded completion
before coherent host readback. `make agx-instruction` runs the combined baseline
and single move-immediate variation. Its full-buffer oracle includes guards,
rounded inactive lanes and a patterned tail in the same allocation.

[Hardware report](../experiments/arithmetic/first-agx-instruction.md) and
[stored verifier](../results/2026-10-04-vulkan-binary-roundtrip/verify_stored.py)
retain the narrow validated field, unchanged controls and stale-digest rejection.
No new GPU run occurred during integration review.
