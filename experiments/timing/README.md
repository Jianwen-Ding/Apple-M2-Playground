# Timing and microbenchmark probes

Priority inherited from the request to investigate time behavior and a possible
special register. No shader time register has been confirmed in this project.

[Driver GET_TIME baseline](driver-time.md) has repeatable read-only samples.
[Shader-counter reconnaissance](shader-counter-candidates.md) retains capability
responses and source concerns but no justified shader timer selector. Selected
source/capability evidence is versioned with those reports; loaded timing and
raw command timestamp validation remain separately owned work.

## Planned sequence

1. Preserve the completed driver-time and P1 parameter controls.
2. Validate command timestamp plumbing against the completed
   [P2 compute/readback control](../baseline/compute-readback.md).
3. Identify candidate special-register reads from primary source code and
   existing reverse-engineering tools; record the exact encoding.
4. Test whether candidate values change monotonically, across lanes, and
   between dispatches; characterize width and wraparound where observable.
5. Compare dependency chains with independent instructions at multiple repeat
   counts, subtract a measured control, and preserve all samples.

Use the [timing method](../../docs/methodology.md). A kernel driver timer and a
shader-readable timer can have different units and scopes. The existence of
`DRM_IOCTL_ASAHI_GET_TIME` in a header does not establish a special register.
