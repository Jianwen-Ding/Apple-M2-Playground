# P1: read-only Asahi device parameters

Completed 2026-10-04. Question: which GPU identity and enabled topology does
the exposed Asahi driver report, and does the installed parameter UAPI work?
The prior hypothesis was the owner-supplied M2 Max target; core count was unknown.
This milestone queries the hardware-facing driver without executing GPU code.

## Reproduce

From the canonical repository `/save/workspace/apple-documentation-playground`:

```sh
python3 -B scripts/run_params.py
python3 -B scripts/run_params.py --device /dev/dri/renderD128 --repeats 3
```

The standalone runner builds `tests/drm_params.c` with the installed headers,
using `CC` (default `cc`) and C11, `-Wall -Wextra -Werror -O2`. It records actual
compiler dependencies and their SHA-256 hashes, compiler/package provenance,
environment, commands, exit statuses, stderr/stdout, and source hashes. It
copies the two DRM headers into its scratch run for reproducibility. Builds
have a 60-second timeout; each query has a 10-second timeout. Repeats are bounded
to 1–10 (default 3). Output differences or changed build dependencies fail the run.
Binaries and complete generated runs stay under `/scratch/apple-m2-playground/runs/`;
`--scratch-root` overrides that root. Integration exposes `make params` and
`python3 -B scripts/run.py params`; `make check` covers this C probe.

Manual equivalent (the outer timeout is part of the experiment bound):

```sh
cc -std=c11 -Wall -Wextra -Werror -O2 tests/drm_params.c -o /scratch/drm_params
timeout 10 /scratch/drm_params /dev/dri/renderD128
```

The program opens with `O_RDONLY|O_CLOEXEC`, verifies `DRM_IOCTL_VERSION` reports
`asahi`, then issues only `DRM_IOCTL_ASAHI_GET_PARAMS`, group 0, with zero padding
and a zero-initialized output structure. No VM, BO, queue, memory mapping,
submission, or time query is performed. `params_raw_hex` preserves all 592 bytes
of the userspace output buffer; scalar fields and all 64 core masks are also
printed. A shorter reported structure fails before full-field interpretation;
a larger structure can expose only the prefix defined by this header.

## Observed driver responses

Three runs on `/dev/dri/renderD128` succeeded with byte-identical stdout. Both
requested and returned structure sizes were 592. The driver was `asahi`, version
`0.0.0`, description `Apple AGX Graphics`; the parameter ioctl number was
`0x40186440` on this aarch64 system.

| Field | Driver-reported value |
| --- | --- |
| Generation / variant / revision | 14 / 67 (`C`) / 17 (`0x11`) |
| Chip ID | `0x6021` |
| Dies / total clusters / logical cores per cluster | 1 / 4 / 10 |
| Active cluster masks | `0x3ff`, `0x1ff`, `0x1ff`, `0x3ff` |
| Remaining 60 mask slots | zero |
| Features | `0x1` |
| Maximum frequency | 1,398,000 kHz |
| Command timestamp frequency | 1,000,000,000 Hz |
| VM start / end / minimum kernel window | 16,384 / 549,755,781,120 / 536,870,912 bytes |
| Maximum commands per submission / attachments | 64 / 16 |

Counting enabled mask bits gives **10 + 9 + 9 + 10 = 38 enabled cores**, with 40
logical slots. This is a count derived from the driver masks, not a shader-based
measurement of physical execution resources. An independent Python little-endian
decode of the raw bytes verified the identity fields, masks, total, and timestamp
frequency, rather than relying solely on the C field printout.

## Interpretation and limits

The installed UAPI defines generation, character variant, BCD revision/chip ID,
and present/enabled core masks. Its revision convention interprets `0x11` as B1.
The inspected local Mesa naming logic maps generation 14 to M2 and variant `C`
to Max, making the reported tuple **G14C B1 / M2 Max**, consistent with the owner
specification. That product-name mapping is a software/source interpretation,
retained with source path, hash, commit and relevant lines in the evidence.
Chip ID `0x6021` is directly reported; no additional independent chip-name lookup
was needed or claimed. Device-tree identity remains unavailable in this container.

This query does not independently establish the computer model, unified-memory
capacity (including the supplied 64 GB claim), current clock, shader behavior,
ISA encodings, performance, or functioning compute submission. Feature bit 0 is
named soft faults by this header, but fault behavior was not exercised. The
timestamp frequency describes firmware command timestamps under this UAPI;
no timestamp was read and no shader counter or instruction timing was established.
Zero-initialized bytes alone do not prove an optional field exists on an older
kernel; reported size and successful field interpretation apply to this run.

## UAPI provenance and compatibility

Compiled header: `/usr/include/drm/asahi_drm.h`, SHA-256
`69fe416b7294dfec4794217bd11379effd53caff4e86010bb803f1b34bdf5e89`.
It is byte-identical to the local Mesa `include/drm-uapi/asahi_drm.h`.
RPM reports `kernel-headers-6.19.6-100.fc42.aarch64` for both DRM headers.
The running kernel is `6.19.14-400.asahi.fc42.aarch64+16k`; the package and kernel
versions differ. Successful group-0 queries and consistent fields establish
compatibility for this operation, not every Asahi ioctl or a globally matching
kernel build. Compiler dependency output records which headers were actually
used; before/after hashes were unchanged. Header snapshots are retained in results.

## Failure checks

| Input | Probe result | Runner result |
| --- | --- | --- |
| Missing `/dev/dri/nonexistent-p1-probe` | status 1, open errno 2 (`ENOENT`) | 1 / FAIL |
| `/dev/null` | status 1, version ioctl errno 25 (`ENOTTY`) | 1 / FAIL |
| `/dev/dri/card2` | status 3, driver `apple` rejected before Asahi query | 1 / FAIL |
| Two positional arguments to C probe | status 2, usage printed | direct invocation |
| `CC=nonexistent-p1-compiler` | compiler launch failure; no device opened | 1 / FAIL |

Failures preserve logs and never produce a parameter PASS. The probe also reports
errno and fails if GET_PARAMS is rejected, refuses short structures, and validates
cluster bounds/mask width before deriving a count. Those GET_PARAMS rejection and
malformed-response branches were inspected but not induced on the working driver.
Permissions failures and timeouts were not observed or simulated. Other agents
may run concurrently; no isolation, idle state, or timing claims are made.

## Evidence and next tasks

Selected raw output, commands, statuses, environment, hashes, header snapshots,
and verification are in
[`results/2026-10-04-device-params/`](../../results/2026-10-04-device-params/README.md).
No vendor sources were modified. The probe agent did not commit or push;
the subsequent integration review is documented in
[progress](../../notes/2026-10-04-probe-progress.md).

Next: P2 should establish bounded compute submission and exact memory readback
on this G14C revision. Timing work can use the reported command timestamp frequency
as metadata, then validate timestamp writes and their units experimentally.
ISA work should keep the 38-core mask topology and revision in run metadata;
prior G13 encodings remain hypotheses until executed on this device.
