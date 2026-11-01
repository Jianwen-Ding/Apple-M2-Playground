# A compute command's end timestamp is written before its memory writes are visible to the CPU

Status: confirmed on one device (M2 Max G14C), our own kernels, commands as zluda_agx submits them. A negative
result for an optimization.

## Claim

The firmware writes a compute command's end timestamp (the per-command timestamp slot zluda_agx binds and zeroes at
submit) about 30 us before the DRM syncobj of the command signals (first seen ~30-50 us after the CPU starts waiting
on a one-thread kernel, the syncobj ~60-80 us). Treating the timestamp as completion is wrong: a kernel that writes
the iteration number to 4 MiB, checked by the CPU after a wait that returns once the end timestamp is non-zero, left
the previous iteration's values in nearly every word, every iteration; the syncobj wait left none in 2000.

## Implications

- Completion must come from the syncobj (or a fence the GPU writes after its caches are written back), not from the
  firmware's end timestamp: the ~30 us between them cannot be saved this way. The timestamps stay good for timing
  and for detecting faulted commands (zluda_agx's use).
- A launch-and-synchronize round trip of an empty kernel costs ~125 us through zluda_agx (~175 us without launch
  batching); most of it is the firmware and kernel path after the command ends.

## Reproducer and evidence

`results/2026-11-01-timestamp-before-visibility/vis.c` (`vis 2000` against zluda_agx's libcuda); the timestamp wait
was a temporary change to agx_runtime `Queue::wait` (spin on the slot's end word, return when non-zero), not kept.
[Evidence](../../results/2026-11-01-timestamp-before-visibility/hardware.txt).
