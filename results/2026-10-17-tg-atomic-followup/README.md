# Retained threadgroup atomic follow-up

27 compressed JSON records, one per tested variant. Each contains the full
program, known-operation control, input words, all available output/table words,
before/after hardware controls, firmware timestamps, kernel-log delta, simulator
gate and memory snapshots. None faulted; all recovery controls passed.

`validation/known-good-after-watchdog-v1.json.gz` contains three known-good
dispatches through the revised bounded watchdog. The deliberately stuck-process
path is tested by host-only mocks, not by inducing a GPU hang.

Run `make verify-tg-atomic-followup` from the repository root. See the
[finding](../../novel-results/2026-10-17-tg-atomic-followup/README.md) for scope.
