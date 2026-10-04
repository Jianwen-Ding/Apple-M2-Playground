# Device parameters — 2026-10-04

Read-only P1 baseline: three identical Asahi group-0 parameter queries reported
G14, variant C, revision `0x11`, chip ID `0x6021`, and masks with **38 enabled cores**.
Local Mesa naming logic interprets this as M2 Max; no shader executed.

Reproduce with `python3 -B scripts/run_params.py` from the canonical repository.
The [experiment report](../../experiments/baseline/device-params.md) distinguishes
driver responses, source interpretation, limits, and follow-up work.

| Evidence | Contents |
| --- | --- |
| `asahi/` | Three raw stdout/stderr pairs, command JSON, compiler/dependency/package logs, source/header hashes, environment and summary; `verification.json` records independent raw-byte decoding and usage failure |
| `missing-device/` | Open failure (`ENOENT`) |
| `non-drm/` | Version ioctl rejection (`ENOTTY`) |
| `wrong-driver/` | Driver `apple` rejected before any Asahi-specific ioctl |
| `missing-compiler/` | Failed compiler launch; no query attempted |
| `headers/` | Exact installed `asahi_drm.h` and `drm.h` used in the successful build |
| `source-interpretation.json` | Local Mesa naming source provenance and relevant lines; software evidence |

Only selected text evidence is retained here. Scratch paths in command logs are
historical; rerunning creates a new scratch directory and binary. Negative-case
summaries deliberately contain `passed: false`. No vendor sources were changed.

Integration review retained fresh success/failure summaries and independent
byte-match verification in `integration-review/`. See
[progress](../../notes/2026-10-04-probe-progress.md) for the shared commands and checks.
