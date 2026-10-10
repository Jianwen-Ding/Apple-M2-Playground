# Command timestamps, fetch-bound straight-line code, and direct DRM compute

Status: confirmed on one device (driver-reported Apple M2 Max G14C B1, kernel
6.19.14-400.asahi, Mesa 25.3.6).

## Claim and scope

1. **Honeykrisp timestamp placement.** A compute timestamp becomes the end of the
   current compute control stream, whatever stage is passed. The usual
   `Write; Dispatch; Write` pair stays at 11–28 µs regardless of work.
   Top-of-pipe followed by a second stamp recorded before the dispatch measures
   the dispatch (linear in work, R² > 0.999).
2. **Timestamp resolution is 24 MHz** (41.67 ns, values truncated to ns). This
   holds for Vulkan queries, raw firmware command timestamps and DRM GET_TIME
   (2,564 values, chance rate 2.4%).
3. **Unrolled straight-line code is fetch bound:** ~3.1 ns + 1.84 ns/byte per
   instruction in the slow clock state. It is independent of dependency chains
   and of active lanes from 32 to 19,456.
4. **Two discrete clock states ~1.65× apart.** Switching to the fast state usually
   happens after a few ms of sustained work, but not always.
5. **A compute dispatch can be submitted with raw ioctls and no Mesa.** The
   results agree with the Vulkan path (slopes within 1%). An empty command costs
   ~5.7 µs of GPU time and ~107 µs host submit-to-signal, about half the Vulkan
   path.

Not established: ALU latency/throughput (needs loops), clock frequencies of the
two states, what triggers a state change, and the meaning of the CDM barrier and
USC unk fields.

## Reproducer and evidence

* Hardware: `make timestamps` (tests/test_command_timestamps.py) and
  `make drm-compute`.
* Offline: `make verify-timestamps`, 21 checks over
  [Vulkan evidence](../../results/2026-10-10-command-timestamps/README.md) and
  [direct DRM evidence](../../results/2026-10-10-direct-drm/README.md).
* Reports: [timing](../../experiments/timing/command-timestamps.md),
  [direct DRM](../../experiments/baseline/direct-drm-compute.md).

## Relationship to existing knowledge

The [earlier source reconnaissance](../../experiments/timing/shader-counter-candidates.md)
predicted compute timestamps would all record the same point. On this driver
they are instead attached to stream ends; this was measured, then explained from
`hk_query_pool.c:383–415`. The UAPI documents timestamps at command granularity.
The 24 MHz grid matches the kernel's CNTPCT-based GET_TIME. The CDM/USC encodings
come from Mesa genxml. Running them with no Mesa code shows those descriptions
are sufficient for a minimal dispatch on G14C.

## Compiler implications and limitations

* For CUDA events: on Honeykrisp use the two-before pattern; on direct DRM use the
  firmware start/end pair. Launch overhead budget: ~6 µs GPU-side and ~0.1 ms
  host-side per command. Batch dispatches into one command where possible.
* Performance work must account for code size. Unrolling costs ~1.8 ns/byte of
  fetch per SIMD group, so 4-byte forms (e.g. short `fadd32` with small
  immediates) are about 1.7× cheaper than 8-byte `iadd` in straight-line code.
  The backend should prefer short encodings and loops over large unrolls.
* Benchmarks must warm up and verify the clock state.
* The direct DRM harness is the starting point for the runtime layer (Stage 3).
  Uniform preload by USC words replaces Honeykrisp's descriptor preamble.
