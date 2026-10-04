# Timing and microbenchmark probes

Priority inherited from the request to investigate time behavior and a possible
special register. No shader time register has been confirmed in this project.

## Planned sequence

1. Read local Asahi time-query and parameter documentation; query supported
   timestamps and frequencies and retain raw values.
2. Establish a command-level baseline after compute submission works.
3. Identify candidate special-register reads from primary source code and
   existing reverse-engineering tools; record the exact encoding.
4. Test whether candidate values change monotonically, across lanes, and
   between dispatches; characterize width and wraparound where observable.
5. Compare dependency chains with independent instructions at multiple repeat
   counts, subtract a measured control, and preserve all samples.

Use the [timing method](../../docs/methodology.md). A kernel driver timer and a
shader-readable timer can have different units and scopes. The existence of
`DRM_IOCTL_ASAHI_GET_TIME` in a header does not establish a special register.
