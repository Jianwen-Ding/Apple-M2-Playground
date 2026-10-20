# Empty-issued return state evidence

Sixteen compressed records: eight empty-issued RET programs and eight
known-state no-return surrogates, each with exact controls before and after.
The matrix covers incoming depths 1..M, M=1..4, with rotations 0 and 1.

Each record retains exact shader/control bytes, input and full output buffers,
source and harness hashes, simulator gates, hypothesis classification,
submission samples and watchdog/kernel/memory/recovery diagnostics. The full
trace at both valid target and bounded fallthrough distinguishes location and
state. Original empty-issued returns preserve state and fall through; known
surrogates expose the distinct `1 -> 0` fallthrough state.

Run `make verify-empty-ret-state` to reconstruct exact programs, resolve source
hashes, independently check every output word and replay the saved behavior.
See the [report](../../novel-results/2026-10-20-empty-ret-state/README.md).
