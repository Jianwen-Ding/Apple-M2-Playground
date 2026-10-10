# Command timestamps and straight-line instruction cost: G14C B1 — 2026-10-10

Driver-reported Apple M2 Max (G14C B1), kernel 6.19.14-400.asahi, Mesa 25.3.6
(Honeykrisp). Every timed dispatch ran native AGX code with an exact whole-buffer
readback oracle. A timestamp was only used when its dispatch proved its results.

## Method

`scripts/run_agx_timestamps.py` uses `patch_body` to replace the pinned control's
`mov_imm r2` with `mov_imm r2, P` followed by N chain steps. It then runs each
variant through `tests/vulkan_timestamp.c`. That harness records four timestamps
per dispatch:

```
t0 = WriteTimestamp(TOP_OF_PIPE)      ; recorded before the dispatch
t1 = WriteTimestamp(COMPUTE_SHADER)   ; recorded before the dispatch
     vkCmdDispatch
t2 = WriteTimestamp(COMPUTE_SHADER)   ; recorded after
t3 = WriteTimestamp(BOTTOM_OF_PIPE)   ; recorded after
```

Host `CLOCK_MONOTONIC` brackets submit and fence wait. Chain kinds, each encoding
decoded back by applegpu before use:

| kind | instruction | bytes | oracle after N steps |
| --- | --- | --- | --- |
| `iadd8` | `iadd rK, 1, rK.sx` | 8 | P + N mod 2^32 |
| `fadd6` | `fadd32 rK, rK, 0.125`, long form | 6 | float(N/8) |
| `fadd4` | `fadd32 rK, rK, 0.125`, short form `2a094482` | 4 | float(N/8) |

`--chains 4` round-robins the steps over r2..r5 (independent dependency chains)
and folds them into r2 at the end.

## Results

All 587 retained samples passed oracles, guards and availability. They are
checked by `make verify-timestamps`.

1. **Timestamps are truncated 24 MHz ticks.** Every one of 2,348 Vulkan timestamps
   satisfies `t == floor(k*125/3)`. So do 216 raw firmware timestamps and DRM
   GET_TIME values from the [direct DRM path](../baseline/direct-drm-compute.md).
   A random value matches with probability 3/125. The resolution is 41.67 ns,
   although `timestampPeriod` reports 1 ns.
2. **The conventional pair measures nothing.** t2 − t1 stays at 11–28 µs for every
   N up to 100,000. Over the same range t1 − t0 grows to 1.19 ms, linearly in N
   (R² = 0.99999 for iadd8). Cause, from Honeykrisp source (`hk_query_pool.c:383–415`):
   a compute timestamp ignores its stage. It becomes the *end* timestamp of the
   current compute control stream, and the next timestamp starts a new stream.
   t1 is therefore the end of the stream that later receives the dispatch. t0 and
   t2/t3 are ends of empty streams.
   **To time a dispatch through Honeykrisp, record two timestamps before it and
   use the first.** `Write; Dispatch; Write` yields only stream overhead. The
   driver never sets the UAPI start timestamp.
3. **Empty compute streams cost about 10 µs of GPU time each** (t3 − t2 medians are
   9–11 µs). The host sees about 125–136 µs median beyond t3 − t0 for submit plus
   fence wait.
4. **Straight-line code is bound by instruction fetch.** Cost per instruction does
   not change with 1 versus 4 independent chains (within 4% for every kind). It
   does not change from 32 lanes (1 SIMD group) to 19,456 lanes (608 groups,
   ~16 per core) either (within 2.3%). Across sizes, slow-state cost fits
   `3.1 ns + 1.84 ns/byte`:

   | kind | slow state, ns/instr | fast state, ns/instr |
   | --- | --- | --- |
   | iadd8 | 17.8 | ~11.7 |
   | fadd6 | ~14 | — |
   | fadd4 | 10.4 | ~6.2 |

5. **There are two discrete clock states about 1.65× apart.** Each process starts in
   the slow state. It usually switches to the fast state after 6–9 back-to-back
   ~0.7 ms dispatches. Once, 64 back-to-back 0.6 ms dispatches never switched.
   Fast/slow medians were 432/712 µs (ratio 1.649, 3 of 60 samples in between).
   GET_PARAMS reports a maximum of 1,398 MHz. One hypothesis, not measured: the
   states are ~1,398 and ~850–970 MHz firmware performance states. The device
   tree is not visible in the container.

## Implications

* For CUDA-event timing on Honeykrisp, use the two-before pattern. On our own
  [direct DRM path](../baseline/direct-drm-compute.md), the UAPI start/end
  timestamp pair brackets a compute command directly.
* Any microbenchmark must control or detect the clock state. Warm up, and check a
  reference kernel's time before and after the measurement.
* Unrolled straight-line code cannot measure ALU latency or throughput, because
  fetch dominates at 1.8 ns/byte even with 608 groups running the same code. A
  latency probe needs a small loop body. Loops are the next control-flow probe.

## Reproduce

```sh
make timestamps          # hardware regression, ~10 ms of shader time
make verify-timestamps   # offline: all claims above against retained evidence
python3 -B scripts/run_agx_timestamps.py --kind fadd4 --chains 4 --lengths 0,32768,65536
```

Evidence: [results/2026-10-10-command-timestamps](../../results/2026-10-10-command-timestamps/README.md).
