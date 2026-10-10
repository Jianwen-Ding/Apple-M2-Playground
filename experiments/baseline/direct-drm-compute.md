# Direct Asahi DRM compute submission (no Mesa, no Vulkan) — 2026-10-10

`tests/drm_compute.c` runs a native AGX compute shader using only kernel ioctls
on `/dev/dri/renderD128`. No Mesa library is loaded. Every hardware word below is
written by hand from Mesa's genxml (`src/asahi/genxml/cmdbuf.xml`) and Honeykrisp
source. That source was read as a reference, not linked. This is the submission
layer a ZLUDA-style CUDA runtime needs, and it removes driver interpretation from
probes.

## What one dispatch needs

| Step | ioctl / structure | Values used |
| --- | --- | --- |
| Device identity | `GET_PARAMS` | G14C rev 0x11, 4 clusters (so G14X CDM form), VA 0x4000..0x7fffffc000, 1 GHz timestamp unit, max 1,398 MHz, soft faults on |
| Address space | `VM_CREATE` | kernel range = top 32 GiB; USC heap at 0x10_0000_0000 (4 GiB); data at 0x11_0000_0000 (Mesa's layout) |
| Memory | `GEM_CREATE` (writeback) + `GEM_MMAP_OFFSET` + `VM_BIND` | USC BO read-only; data BO read/write; 16 KiB pages |
| Timestamps | `GEM_BIND_OBJECT` (USAGE_TIMESTAMPS) | firmware writes start/end u64 at offsets 0/8 |
| Queue | `QUEUE_CREATE` | priority medium, `usc_exec_base` = USC heap base |
| Work | `SUBMIT` with one `DRM_ASAHI_CMD_COMPUTE` | `cdm_barrier` 0, `vdm_barrier` NONE, out-syncobj |

USC addresses (shader code and pipeline words) are 32-bit offsets from
`usc_exec_base`.

### USC pipeline words (at USC offset 0x1000)

```
1d 08 80 00 00 00 00 11   Uniform: start half 8 (u4), 8 halfs, buffer = data+0 (VA>>2 at bit 26)
4d 90 00 00               Shared: none (layout 0x24 vertex/compute, 65536 B encoded as 0)
0d 0c 00 20 00 00         Shader: unk_2=3 (compute), code at USC offset 0x2000
8d 01 00 01               Registers: count 1 group of 8 (16 with --gprs 16), unk_4=1
88 00                     No preshader
```

The uniform buffer holds u4 = 0 (index offset), u5 = count and u6_u7 = output VA.
Since the load-latency work, the word preloads 12 halfs: u8_u9 is the VA of an
optional table file copied to data BO + 1 MiB (`drm_compute ... gprs table.bin`).
That is exactly what the pinned control's main reads. Honeykrisp's preamble
normally loads them from its descriptor tables. Here they come straight from
memory, so the main runs unchanged with no preamble.

### CDM control stream (data + 0x4000)

```
02000000                  Launch word 0: uniform register count 1 group (<=64 halfs), direct mode
00100000                  Launch word 1: pipeline = USC offset 0x1000
00000000 00000040         G14X-only word (bit 62 set), required on 4-cluster parts
<rounded> 1 1             Global size in threads
32 1 1                    Local size
ffff0f60                  Barrier: Mesa's unk0..19 incl. USC cache invalidate
00000040 00000000         Stream terminate
```

## Results

| Run | Lanes | Oracle | Firmware command time | Host submit→signal |
| --- | --- | --- | --- | --- |
| control main | 33, 257 | whole buffer exact | 5.8–7.6 µs | 107–660 µs |
| fadd4 chain 0..65536 | 32 | exact | 10.46 ns/instr slope | — |
| iadd8 chain 0..32768 | 32 | exact | 17.66 ns/instr slope | — |

* **It worked on the first submission.** None of the ~20 submissions so far
  produced a fault or timeout. (dmesg needs root, so this is from return codes and
  oracles, not a kernel log.)
* **Chain slopes match the Vulkan path within 1%**, including the clock-state
  switch. The [timing results](../timing/command-timestamps.md) therefore reflect
  hardware, not Mesa.
* **A near-empty compute command is ~5.7 µs of GPU time**, measured from the
  firmware start/end pair, which Honeykrisp never requests. Host latency for an
  empty dispatch is about 107 µs, half of the Vulkan path's ~215 µs. It is noisy:
  identical dispatches took 115 or 577 µs host-side in one run. Prefer firmware
  timestamps.
* The firmware timestamps and `GET_TIME` share the 24 MHz grid and epoch, so
  host-side `GET_TIME` brackets are directly comparable.

## Not yet established

* Which CDM barrier bits are needed. Mesa sets all of 0..19 "to be safe".
* Whether the G14X word is mandatory. It was always sent; omitting it is untested.
* Meaning of USC `Shader.unk_2`, `Registers.unk_4`, the `Launch` uniform-count
  semantics above 64 halfs, preshaders, threadgroup memory, textures/samplers and
  the helper program (scratch/stack). All of these are unused here.
* Multiple launches per stream, multiple commands per submit, and in/out sync chains.

## Reproduce

```sh
make drm-compute    # control + fadd4/iadd8 chains through the direct path
python3 -B scripts/run_drm_compute.py --kind control --count 257
```

Evidence: [results/2026-10-10-direct-drm](../../results/2026-10-10-direct-drm/README.md).
