# Apple M2 Playground

Task 1 workspace for probing Apple AGX on Asahi Linux. The project target is an
M2 Max with 64 GB of unified memory, as supplied by the project owner. The
current container exposes Asahi driver parameters for G14C revision `0x11`,
chip `0x6021`, with 38 enabled cores derived from its masks. Local Mesa naming
logic interprets this as M2 Max; the 64 GB capacity has not been measured.

The goal is reproducible hardware observations that can guide PTX translation
and an AGX compiler backend. Read-only parameter and driver-time probes establish the baseline;
no new instruction behavior has been demonstrated yet.

## Layout

| Folder | Contents |
| --- | --- |
| `docs/` | Probe roadmap, measurement method, and source references |
| `environments/` | Requirements and setup for Linux hardware and offline work |
| `experiments/` | Plans and future runnable probes grouped by subject |
| `tests/` | Reusable smoke tests and regressions for confirmed behavior |
| `scripts/` | Environment capture and repeatable probe runners |
| `notes/` | Session notes, limitations, and failed approaches |
| `results/` | Selected environment snapshots and raw evidence worth keeping |
| `novel-results/` | New hardware findings, each paired with a reproducer |
| `templates/` | Experiment and finding report templates |

Source, notes, and selected evidence belong in Git. Regenerable binaries and
bulk run output belong in `/scratch/apple-m2-playground/`, which persists
across sessions but has no version control.

## Starting points

From this repository:

```sh
make env     # Record available tools, device nodes, kernel, and header hashes
make check   # Python/C syntax checks; no GPU device access
make smoke   # Build and run the DRM driver-access test
make params  # Three read-only Asahi identity/topology queries
make time    # 264 bounded driver timestamp queries; no shader execution
```

Run records and binaries go to `/scratch/apple-m2-playground/runs/`.
Override with `make smoke DEVICE=/dev/dri/renderD128 SCRATCH_ROOT=/scratch/other`.
Python-only equivalents are documented in [scripts/README.md](scripts/README.md).

- [Probe plan](docs/probe-plan.md)
- [Asahi Linux environment](environments/asahi-linux/README.md)
- [Offline environment](environments/offline/README.md)
- [DRM probe tests](tests/README.md)
- [Device parameters and evidence](experiments/baseline/device-params.md)
- [Driver time and evidence](experiments/timing/driver-time.md)
- [Reviewed progress and next tasks](notes/2026-10-04-probe-progress.md)
- [Known limitations and failed approaches](notes/failed-approaches.md)
- [Timing investigation](experiments/timing/README.md)

Every report should distinguish a planned hypothesis, a software-model result,
an observed hardware result, and a confirmed finding. A successful DRM version
query proves device access; it does not prove shader execution.

The initial `test.txt` is the repository push smoke-test artifact.
