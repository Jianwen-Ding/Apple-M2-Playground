# Published knowledge versus our measurements (survey 2026-10-16)

This survey was run before the safe probe tasks (simulator `tasks/safe-07` .. `safe-12`). It lists what public sources
say about the AGX GPU, Apple GPUs in general and the Asahi DRM interface, and where that agrees or disagrees with what
this repository measured on the M2 Max (G14C B1). Treat published values as claims, not evidence. Most of them were
measured on other chips (M1, M2 Pro) or through Metal.

## Sources consulted

- **[applegpu ISA docs](https://dougallj.github.io/applegpu/docs.html)** (Dougall Johnson). G13 / M1, reverse
  engineered.
- **[philipturner/metal-benchmarks](https://github.com/philipturner/metal-benchmarks)**: Metal microbenchmarks for
  Apple 7 / 8 (M1 / M2).
- **[Chips and Cheese, "A brief look at Apple's M2 Pro iGPU"](https://chipsandcheese.com/p/a-brief-look-at-apples-m2-pro-igpu)**:
  OpenCL / Vulkan measurements.
- **The upstream Asahi UAPI:**
  - [`include/uapi/drm/asahi_drm.h`](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/drm/asahi_drm.h)
    (now in mainline);
  - the [v1-v6 review thread](https://lkml.iu.edu/hypermail/linux/kernel/2503.3/05553.html), March 2025.
- **Asahi progress reports:**
  - [Linux 6.16](https://asahilinux.org/2025/08/progress-report-6-16/): Mesa drivers are upstream and the fork is
    retired.
  - [Linux 6.19](https://asahilinux.org/2026/02/progress-report-6-19/): the GPU driver is about 21,000 lines; M1 / M2
    have Vulkan 1.4 (Honeykrisp), GL 4.6 and OpenCL; M3 has no GPU driver yet.
- **[Alyssa Rosenzweig, "Dissecting the Apple M1 GPU, part III"](https://rosenzweig.io/blog/asahi-gpu-part-3.html)**:
  register file and occupancy on M1.
- **[Mesa asahi MR 215](https://gitlab.freedesktop.org/asahi/mesa/-/merge_requests/215)**: "magic" helper memory
  barriers needed for texture atomics on G13X, found by guesswork.
- **CUDA on Apple GPUs.** Nothing published targets PTX → native AGX:
  - the existing projects go through Metal or through SPIR-V → MoltenVK (OpenFPM, CuMetal);
  - ZLUDA itself targets AMD only.
  Our route (PTX → LLVM → AGX on Asahi) has no public precedent.

## Comparison

| Topic | Published | Ours (M2 Max, direct DRM) | Status |
|---|---|---|---|
| Register file | ~208 KB per core (metal-benchmarks); "208 KiB" inferred on M1 (Rosenzweig) | 3,328 halves × 32 lanes × 2 B = 208 KiB, allocated to pairs of SIMD groups (`novel-results/2026-10-11-occupancy`) | **agrees**; pair granularity is ours |
| Max threads per core | 384-3,072 | 96 SIMD groups = 3,072 threads, formula per register count | **agrees** |
| GPRs per thread | up to 128 (r0-r127) (applegpu) | 248 halves (124 registers) is the largest non-wrapping launch value | consistent |
| Uniform registers | 256 × 32-bit (u0-u255) (applegpu) | not swept | **safe-09 should sweep u0-u255 only** |
| Threadgroup memory | ~60 KB per core (metal-benchmarks); 32 KB per allocation (Metal / OpenCL limit) | 64 KiB per core, 256-byte allocation granule (occupancy finding) | **differs**: published figures are API limits; ours is the hardware |
| L1 data cache | 8 KB (both sources) | not measured directly | safe-03 |
| Global cache line | 128 B (metal-benchmarks) | **64 B at L1, L2 and SLC / DRAM fill** (`novel-results/2026-10-16-cache-line`) | **differs** |
| L2 | ~1 MB for M2 Max (metal-benchmarks); 3 MB on M2 Pro (Chips and Cheese, probably GPU-visible L2 + something else) | L2 93-123 ns to 256 KiB, spilled by 1-2 MiB (`novel-results/2026-10-16-memory-parameters`) | **agrees with ~1 MB** |
| SLC | 48 MB on M2 Max | latency rises only ~12% from 16 to 96 MiB, so capacity is not readable from latency (`2026-10-16-memory-parameters`) | open: needs a bandwidth probe |
| Latencies | SLC 234 ns, DRAM 342 ns (128 MB), > 400 ns beyond (TLB?) (M2 Pro) | DRAM ~378 ns at 128 MiB; TLB adds ≤ 32 ns over 256 MiB | close; TLB reach still open |
| Global atomics | 58.6 ns latency (M2 Pro); only 32-bit atomics; **M2 adds a non-returning u64 min/max** | **u64 min / max found: op 3 (cmpxchg) + bit 45, bit 46 = max**; with Rt = 1 it returns a changed flag, not the old value. Also a **float32 atomic add** (op 1 + bit 45). Ops 11-15 end the SIMD group (`novel-results/2026-10-17-atomic-variants`) | **agrees** (not among ops 11-15) |
| Clock | 1.398 GHz M2 Max | GET_PARAMS max_frequency 1,398 MHz; battery clock states | agrees |
| ALU latencies | FFMA32 2.2 cycles, IMAD32 4, CONVERT 3.66, RCP 6.5, RSQRT 9, EXP2 / LOG2 4.3 | instruction-bench coverage (651 forms) | cross-check in safe-02 |
| Convert semantics | applegpu: TODO; float destinations: f32 with FTZ, f16 without | 80 forms recorded on random operands | **safe-01 is new knowledge** |
| Memory barriers | applegpu documents none; Mesa names f533 / f59d "unknown"; MR 215 adds helper barriers by guesswork | f533 = cross-core release, f59d = acquire / invalidate (`2026-10-11-memory-ordering`) | **ours is new**; safe-10 extends it |
| Preamble | not documented publicly (only Mesa source) | once per core, one lane, slot 96 | ours is new |
| Undecoded opcodes, fmadd lane offset | not documented | our findings | new |
| Queue priority | LOW 0, MEDIUM 1; HIGH 2 and REALTIME 3 are "reserved for future extension" | harness uses 0 / 1 | safe-04: expect 2 / 3 to be rejected host-side |
| Command timestamps | `command_timestamp_frequency_hz` must be queried | already printed by `drm_compute` | use it in all timing |
| Sync | binary and timeline syncobjs, in / out in one SUBMIT array | unused | safe-12 §4 |
| VM bind | READ / WRITE / UNBIND / **SINGLE_PAGE** (one page repeated over a range) | READ \| WRITE only | safe-12 host-side probe |
| GEM | WRITEBACK, VM_PRIVATE | WRITEBACK only | safe-12 |
| Submission limit | `max_commands_per_submission` in params | not read yet | safe-04 §4, safe-12 |

## Consequences for the tasks

- **safe-03:**
  - expect a 128-byte line;
  - the SLC is expected near 48 MB, so sweep footprints up to 96 MiB as planned;
  - Chips and Cheese's > 400 ns beyond 128 MB is a TLB hint worth reproducing.
- **safe-09:** uniform sweep bounded to u0-u255.
- **safe-04 / safe-12:**
  - read `max_commands_per_submission` before N > 1;
  - priorities 2 / 3 are reserved;
  - syncobjs are the event mechanism.
- **Device atomics:** the non-returning 64-bit min / max of M2 (Apple 8) was located through applegpu's `u5` note
  and run with owner approval on 2026-10-17: op 3 + bit 45 (`novel-results/2026-10-17-atomic-variants`).
- **Novelty:** convert semantics, fences, preamble, undecoded opcodes, lane-offset fmadd and the direct-DRM interface
  details have no public description. These are the most valuable outputs.
