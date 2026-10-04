# Apple M2 Playground

Task 1 workspace for probing Apple AGX on Asahi Linux. The project target is an
M2 Max with 64 GB of unified memory, as supplied by the project owner. The
current container has an accessible Asahi DRM render node; exact GPU identity
and enabled core count still need a device-parameter query.

The goal is reproducible hardware observations that can guide PTX translation
and an AGX compiler backend. Initial work establishes the test environment;
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

- [Probe plan](docs/probe-plan.md)
- [Asahi Linux environment](environments/asahi-linux/README.md)
- [Offline environment](environments/offline/README.md)
- [DRM smoke test](tests/README.md)
- [Known limitations and failed approaches](notes/failed-approaches.md)
- [Timing investigation](experiments/timing/README.md)

Every report should distinguish a planned hypothesis, a software-model result,
an observed hardware result, and a confirmed finding. A successful DRM version
query proves device access; it does not prove shader execution.

The initial `test.txt` is the repository push smoke-test artifact.
