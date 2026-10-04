# Asahi driver time query — 2026-10-04

Question: does the exposed Asahi GET_TIME ioctl work, and does its returned
nanosecond timestamp advance at the host elapsed-time rate?
Pre-run hypothesis: a supported timer should be nondecreasing, with approximately
one returned nanosecond per CLOCK_MONOTONIC_RAW nanosecond over paced samples.
This hypothesis concerns the driver timer only, not a shader special register.

## Reproducer and bounded scope

From the canonical `/save/workspace/apple-documentation-playground` repository:

```sh
python3 -B scripts/run_time.py
python3 -B scripts/run_time.py --device /dev/dri/nonexistent-time-probe
```

The runner builds `tests/drm_time.c` with C11, warnings as errors, and O2 into
a unique scratch directory. It records environment, commands, exit codes,
source hashes, JSON-line samples, and analysis. Compilation has a 60-second
limit; each invocation has a 10-second limit. A DRM VERSION control requires
`asahi` before any device-specific ioctl. The only ioctls are VERSION and
GET_TIME with zero flags. No VM, allocation, submission, shader, or reset occurs.

Successful phases: eight warmup reads, 128 unpaced reads, and two independent
processes taking 64 reads each with requested 10 ms sleeps between reads.
These are 264 queries total; they do not establish long-term behavior.
The C interface bounds each invocation to 2–256 samples and 0–20 ms spacing
(maximum requested sleep total 5.1 seconds). It stops on the first ioctl error.
The reviewed runner requires the expected 8/128/64/64 successful records and
valid metadata, sequential indices, integer sample fields, and ordered host
brackets. Empty/malformed/truncated output and nonpositive elapsed time fail
with a retained summary. It stops on command failure or backward time. It preserves numeric errno and
stderr; it does not silently replace failed timestamps with zero.

## Hardware observations

Raw evidence: [retained run](../../results/2026-10-04-driver-time/success/summary.json)
and all adjacent phase stdout files. Kernel:
`6.19.14-400.asahi.fc42.aarch64+16k`, aarch64, render node `/dev/dri/renderD128`.
VERSION returned driver `asahi`; GET_TIME request number 3222299713, structure
size 16 bytes. All 264 reads succeeded with flags zero. Each phase was strictly
increasing: zero backward or equal steps. Device-tree identity was unavailable;
the owner-specified M2 Max is not independently verified by this experiment.

| Phase | Samples | Returned elapsed ns | Host elapsed bracket ns | Returned ns / host ns, midpoint |
| --- | ---: | ---: | --- | ---: |
| Warmup | 8 | 8667 | 8125–10250 | 0.943346939 |
| Burst | 128 | 77333 | 76917–78041 | 0.998115618 |
| Paced | 64 | 635031917 | 635030292–635033251 | 1.000000229 |
| Paced repeat | 64 | 633952708 | 633950834–633954208 | 1.000000295 |

For first and last samples, each timestamp is assumed to be taken inside its
host before/after ioctl bracket. Elapsed-time bounds are last-before minus
first-after, and last-after minus first-before. Ratio brackets for the paced
runs are [0.999997899, 1.000002559] and [0.999997634, 1.000002956]. These are
bracketing calculations, not statistical confidence intervals. Both include 1.
Warmup and burst illustrate why a short host interval is a poor rate estimate.

The smallest observed consecutive returned delta was 541 ns in the burst;
it is not timer resolution or instruction latency. All returned values have
residue 0, 41, or 83 modulo 125, compatible with flooring a 24 MHz counter into
nanoseconds. This compatibility is not an independent measurement of frequency
or proof that a shader can read that counter. A 64-bit UAPI field does not prove
physical counter width, wrap period, or atomic shader read semantics.

Observed host ioctl brackets ranged from 292 to 4458 ns across phases. They
include host clock reads, syscall/driver work, and scheduling effects. They are
not GPU ISA latency. Logs/output formatting also perturb inter-query spacing.
No controlled GPU clock, temperature, workload, or isolation measurement was
made; concurrent agents were active. No suspend, long idle, or wrap test ran.

## Source evidence and limits

Installed `/usr/include/drm/asahi_drm.h`, vendor Mesa's UAPI header, and the
pinned Asahi kernel UAPI are byte-identical, SHA-256
`69fe416b7294dfec4794217bd11379effd53caff4e86010bb803f1b34bdf5e89`.
UAPI defines GET_TIME output in nanoseconds. Command execution timestamps have
a separate firmware-controlled `command_timestamp_frequency_hz`; that value
must be queried before interpreting command timestamp readback.

The pinned [Asahi implementation](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/gpu/drm/asahi/file.rs#L1055)
rejects nonzero flags, reads ARM `CNTPCT_EL0`, and computes
`raw * (1e9/gcd(base_clock_hz,1e9)) / (base_clock_hz/gcd(...))`.
The retained [T602x configuration](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/gpu/drm/asahi/hw/t602x.rs#L55)
excerpt sets `base_clock_hz = 24_000_000` for **T6022 / G14D**, giving integer
conversion `raw * 125 / 3`. That excerpt does not establish the setting for
this device's reported T6021 / G14C; 24 MHz remains a source hypothesis compatible
with the observed timestamp lattice.
The driver table permits GET_TIME on render nodes. Exact running kernel build
source was unavailable under `/usr/src`; matching UAPI establishes ABI
compatibility, not exact implementation identity. The source explains a
plausible mechanism consistent with measurements, not a demonstrated GPU ISA
counter. Immutable URLs, file hashes, and relevant excerpts are retained in
[source evidence](../../results/2026-10-04-driver-time/source-evidence.json).

Vendor Mesa at `e5f0687867f5c5e88619175d9b0442f8560e8d53` calls GET_TIME in
`src/asahi/lib/agx_device.c:874`. Its `hk_physical_device.c:114` disables
KHR_shader_clock and lines 445–447 disable both shader clock features.
The inspected applegpu `SR_NAMES` map (`applegpu.py:24`) contains no identified
timer, and its `get_sr` model only handles SR80 (`:2373`). These are software
support limitations, not proof that hardware lacks a readable counter. Neither
vendor repository was modified.

## Failure evidence and verification

The retained missing-device run returned status 1 with
`open(/dev/dri/nonexistent-time-probe): errno=2 No such file or directory`.
It preserves compile/control logs and failed summary. Argument checks reject
257 samples, 21 ms spacing, and nonnumeric sample count with status 2, before
opening hardware. C syntax check with warnings as errors passed; Python parsed
successfully. Synthetic analysis checks verified unit rate and backward-step
detection. See [verification](../../results/2026-10-04-driver-time/verification.json).
No unsupported GET_TIME error occurred. No recovery or reset was needed.
An absent `/usr/include/libdrm/asahi_drm.h` was resolved by using the installed
`/usr/include/drm/asahi_drm.h`. Kernel source directories were empty; remote
immutable source inspection therefore carries the build-match limitation above.

## Next timing tasks

1. Use the completed [P1 parameters](../baseline/device-params.md): G14C
   revision `0x11`, 38 enabled mask bits, command timestamp frequency 1 GHz.
   This frequency is driver metadata; command timestamp readback still needs
   validation. Do not substitute maximum GPU frequency for timer frequency.
2. Once compute submission and exact buffer readback pass, request supported
   start/end command timestamps for a minimal control and bounded workloads.
   Convert using the queried command frequency; preserve raw ticks, completion
   status, and controls. This establishes command timing, not instruction cycles.
3. Identify an exact candidate shader counter from a primary disassembly,
   compiler implementation, or hardware trace for the confirmed GPU generation.
   The ARM `CNTPCT_EL0` name does not supply an AGX special-register number.
   No justified shader counter index was found here; do not scan unknown SRs or
   emit random instructions. Retain candidate bytes and provenance before use.
4. Test the justified candidate with a small bounded shader: read twice, store
   both values per lane, and validate readback. Compare lanes and dispatches;
   establish width, monotonicity, rate, wrap handling, and read overhead before
   inserting dependency chains. For split words use a source-supported atomic
   method or bounded high/low/high retry; do not assume a 64-bit atomic read.
5. Only after counter validation, compare known instruction chains and
   independent sequences at bounded repeat counts against the same unchanged
   timer-read control. Preserve samples and distinguish timer ticks from cycles.

## Integration review

The original raw 264-sample evidence passes the corrected structural validator.
A bounded rerun again validated all 264 successful samples with no backward or
equal steps; both paced ratio brackets include 1. Updated raw output, hashes,
summary, `/dev/null` failure, and synthetic failure checks are retained under
[`integration-review/`](../../results/2026-10-04-driver-time/integration-review/verification.json).
See [progress](../../notes/2026-10-04-probe-progress.md) for checks and next tasks.
Historical source hashes in the original run describe its original code;
reviewed rerun hashes describe the corrected code.
