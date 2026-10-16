# On battery, sustained GPU load lowers the clock ~2.1x; Vulkan device 0 can silently be llvmpipe

Status: observed on one device (driver-reported M2 Max G14C B1, Mesa 25.3.6 Honeykrisp) on battery power (AC offline,
57 %, discharging). Not yet repeated on AC power.

## Claim

1. **Three clock states on battery, chosen by recent load.** A fixed sgemm dispatch (2.147 GFLOP) runs in ~1720 µs,
   ~2730-2900 µs or ~3642 µs (2.12x the fast state). This is a timed command-stream interval (24 MHz firmware ticks),
   with the output checked.
   - After ≥ 0.3 s of back-to-back submissions, every following run is slow.
   - Runs separated by short host gaps (buffer re-initialisation, about 50-70 % GPU duty) mostly settle in the fast
     state after 1-2 submissions.
   - The first submission after ~3 s of idle is often slow.

   The fast state matches the cost model's top-clock (1398 MHz) prediction (2070 µs predicted, 1.2x).

   This is the opposite of the 2026-10-10 [command-timestamp](../../experiments/timing/command-timestamps.md)
   observation: there, the GPU started slow and became fast after 6-9 back-to-back dispatches. The power source of that
   session was not recorded. Sustained load on battery appears to hit a power limit; on AC the ladder may behave like the
   earlier report.
2. **Default Vulkan device 0 was llvmpipe for a few minutes.** Around a display power-off (apple-dcp in the kernel log),
   a runner that took physical device 0 got llvmpipe instead of the AGX. Its results were correct (relative error 6e-7
   against an fp64 reference) and its output is bit-identical to a forced-lavapipe run. Only these give it away:
   ~60 ms host time per submit, 40-250 ns "GPU" timestamps, and 42 W system power (all CPU cores).

## Consequences for benchmarking (CUDA events, autotuning)

- Report a clock state with every timing. Take the fastest cluster of runs (within 5 % of the minimum), or record the
  power source and state. A plain median over a sustained loop measures the power-limited state on battery.
- Do not warm up with sustained back-to-back load on battery: it lowers the clock.
- Always check the device name or type (`VK_PHYSICAL_DEVICE_TYPE_CPU`) before trusting a result. A ZLUDA runtime
  choosing a Vulkan / DRM device must never fall back silently.

Total system power and heatpipe power are readable without root from `macsmc_hwmon`
(`/sys/class/hwmon/hwmon*/power1_input`, `power4_input`, in µW). The battery and AC state are in
`/sys/class/power_supply/macsmc-{battery,ac}`.

## Reproduce

```sh
make verify-battery-clock-states   # offline, the retained sequences
```

Hardware: AGX-Performance-Simulator `tests/vk_run.c` with an sgemm-large spec, `warmup 0|300|1000`, `repeat 10`,
3 s idle between processes. Evidence: [results/2026-10-16-battery-clock-states](../../results/2026-10-16-battery-clock-states/evidence.json).
The simulator's re-timing of all 177 workloads is in AGX-Performance-Simulator `results/2026-10-16-asahi-retime`.
