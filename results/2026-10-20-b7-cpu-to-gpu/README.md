# B7: which GPU loads see host writes made during a dispatch (2026-10-20)

Blocker B7 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: only `f59d` followed by a coherent
`device_load` (Mesa u4 = 7) sees CPU stores while the kernel runs.** This confirms, in a separate harness, the CPU->GPU
half of `novel-results/2026-10-16-cpu-gpu-visibility` (round trip < 1 us), and adds what does *not* work.

`b7.py`: `tests/drm_compute.c`'s `AGX_CPU_CLOCK` thread increments table word 0 continuously during the dispatch
(WRITEBACK BO, CPU cached). 64 lanes each read it N = 20,000 times with one load variant and output last - first.
Each program ran in `agx_run` first (no CPU thread there: delta 0). One GPU run each, AC power, 0 faults.

| Read per trip | CPU `dc cvac` per write | Delta seen by the GPU | Firmware time (20,000 trips) |
| --- | --- | --- | --- |
| plain `device_load` | no / yes | **0 / 0** | 3.8 ms |
| returning atomic add of 0 | no / yes | **0 / 0** | 5.3 / 8.7 ms |
| coherent `device_load` (u4 = 7), no fence | no | **0** | 3.4 ms |
| `f59d` + plain `device_load` | no | **0** | 4.2 ms |
| **`f59d` + coherent `device_load`** | no | **425,749-425,758** (all 64 lanes) | 13.8 ms (0.69 us per trip) |

So host writes are not visible mid-dispatch to plain loads, coherent loads without the fence, or even device atomics
(which return the value from the GPU side of the hierarchy). A CPU-side cache clean does not change that.

**Lowering for PTX:** `ld.volatile.sys` / `ld.acquire.sys` (and polling a host-written flag in mapped memory) =
`f59d` + coherent `device_load`; the store side (`st.release.sys`, `__threadfence_system()`) = coherent store + `f533`
(2026-10-16 finding). The `.sys` scope for B10 is these two sequences.
