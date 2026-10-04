# Minimal DRM smoke test

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
