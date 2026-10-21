# B35: no special register is a clock (2026-10-21)

Blocker B35 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM, battery power. 256
dispatches, 0 faults; hang budget unchanged.

**Result: no `get_sr` selector counts time.** Every selector 0..255 was read twice by the same thread, 0.96 ms apart
(firmware time 962-975 us per dispatch), and only **SR113** changed (0 -> 8 on every lane), which is the known global
power-state bit (`novel-results/2026-10-16-special-registers`), not a counter. Every other selector read the same
value before and after, matching the published compute map (SR4-10 sizes, SR15 = 16, SR16 = lane & 3, SR19 = 32,
SR21 = VM slot, SR24/25 = 2, SR32 = pipeline offset, SR48-59 lane / quad ranks, SR60 = 15, SR63 = 1, SR80 = thread id,
SR97 = 2048, SR114 = 136, the rest 0).

**What ZLUDA can use instead:** the CPU-written timer of `novel-results/2026-10-11-in-shader-clock` and
`2026-10-18-clock-load`. A host thread writes `CNTVCT_EL0` (24 MHz, 41.7 ns per tick) into a GPU-visible buffer, and
the shader reads it with `f59d` (device_barrier_1) + a coherent `device_load` (u4 = 7) + `wait 0`, at 0.6-1.0 us per
read, with one timer line per core group to avoid contention. That serves `%globaltimer` (scaled to ns) and a coarse
`clock64()`. There is no cycle counter, so `%clock` / `%clock64` can only be derived from that timer (or kept at 0, as
ZLUDA does now). `nanosleep` can spin on the same timer for a bounded number of reads.

Probe: `b35.py sim|gpu TRIPS`: `get_sr sel -> r6`, a counted loop of TRIPS x 8 dependent `fmul32`, `get_sr sel -> r7`;
r6 and r7 stored per lane. Checked in `agx_run` first (`AGX_SR_DEFAULT=0`). `gpu.json` holds the values and firmware
times.
