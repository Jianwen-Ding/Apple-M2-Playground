# Read-only DRM probes

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
