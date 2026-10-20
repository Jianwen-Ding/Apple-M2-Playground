# B25: GPU telemetry Asahi exposes to userspace (2026-10-20)

Blocker B25 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. Read-only; no GPU work submitted.
Checked as the unprivileged container user on the M2 Max (kernel 6.19.14-400.asahi.fc42, AC power).

**Result: almost nothing GPU-specific is exposed.** NVML can report max clock and (in-process) busy time; not
current clock, temperature or GPU power.

| NVML quantity | Source | Unit | Root needed | Available |
| --- | --- | --- | --- | --- |
| Max graphics clock | `DRM_ASAHI_GET_PARAMS.max_frequency_khz` | kHz (1,398,000) | no | yes |
| Current graphics clock | no devfreq node, no sysfs file for the asahi device | - | - | **no** |
| Utilization | sum of firmware command timestamps (start/end per command) over a wall interval | 1 GHz ticks (`command_timestamp_frequency_hz` = 1e9; `GET_TIME` advances 1.000007 ticks per host ns) | no | own process only |
| GPU temperature | `/sys/class/hwmon`: only NAND, battery hotspot, charge regulator, WiFi/BT; `thermal_zone0` = battery | - | - | **no** |
| GPU power | `macsmc_hwmon` power1 Total System Power, power4 Heatpipe Power (SoC heat-pipe rail, not GPU-only) | uW | no | proxy only |
| Runtime PM | `/sys/class/drm/card1/device/power/runtime_status` = unsupported | - | - | no |

`/sys/kernel/debug` is empty in this container (debugfs not mounted). `/proc/device-tree` is not visible, so the
GPU's performance-state table cannot be read here; a host with device-tree access may expose the OPP list.

`params.json` (from `params.c`):
- `features` = 1: **`DRM_ASAHI_FEATURE_SOFT_FAULTS` is set** (answers B20 step 1: unmapped loads return 0,
  unmapped stores are dropped, so an out-of-bounds access may not fault at all);
- G14 variant 'C' (67) revision 17 (B1), chip 0x6021, 1 die, 4 clusters x 10 cores, core masks
  0x3ff, 0x1ff, 0x1ff, 0x3ff (38 cores);
- VM 0x4000 .. 0x7fffffc000, 64 commands per submission, 16 attachments.

`macsmc_hwmon.txt` is one snapshot of every labelled SMC sensor.

**For zluda_ml_agx:** implement `nvmlDeviceGetMaxClockInfo` from GET_PARAMS; `GetClockInfo` can only report the
max; `GetUtilizationRates` from the runtime's own command timestamps; `GetTemperature` stays `NOT_SUPPORTED`;
`GetPowerUsage` could report Heatpipe Power as a labelled SoC proxy or stay `NOT_SUPPORTED`.

**For the simulator's clock question (S1):** userspace cannot read the operating frequency. It has to be
inferred in-shader (safe-11's in-shader clock against the 1 GHz firmware timebase).
