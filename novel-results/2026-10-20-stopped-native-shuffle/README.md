# Stopped sources also self-fallback in relative, xor and rotate shuffles

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**160 variants / 480 dispatches with exact controls, zero faults.**

Native `simd_shuffle_down`, `simd_shuffle_up`, `simd_shuffle_xor` and
`simd_shuffle_rotate_up` also return the issuing lane's own A value when the
selected source has stopped. Living masked sources remain readable. This is
measured separately from [plain shuffle](../2026-10-20-stopped-shuffle-index/README.md),
rather than inferred from a common encoding.

For each form, compare immediate and uniformly seeded register indices before
partial STOP and after pop 1 activates survivors. Payloads are unique lane IDs
initialized in all physical lanes before divergence. Incoming maximum depths
are 1 and 3, with rotations 0 and 1. Ten offsets cover zero, adjacent lanes,
quad boundaries, half groups and edges: 0,1,2,3,4,7,8,15,16,31. Down/up out-of-
range targets retain the issuing value; rotate-up wraps modulo 32; xor stays
in range. Each program finishes with four more pops and a survival marker.
Candidate and exact wait control differ only in the STOP/wait instruction.

All complete shaders first pass the recorded simulator source hypothesis.
Each form's first offset-1 case was inspected before extending the matrix.
Independent full-buffer oracles check every source/writer value, both paired
forms, inactive destinations, inputs, final markers, main output and guards.
All controls and retained watchdog/kernel/memory/recovery diagnostics pass.
No fault or hang occurred. Stopped lanes remain absent at the final marker.

Uniform indices do not distinguish stopped-lane contributions to the quad's
low-index OR. The [plain-shuffle index-OR finding](../2026-10-20-dead-index-or/README.md)
therefore still requires native-form follow-up. Simulator bf03118 has not yet
been changed for these four forms; the source-liveness counterexamples remain
explicit in `make verify-stopped-native-shuffle`. No terminated register
storage or timing claim is made.

```sh
python3 -B scripts/probe_stopped_native_shuffle.py --kind rotate_up --hardware
make verify-stopped-native-shuffle
```

[Full evidence](../../results/2026-10-20-stopped-native-shuffle/README.md).
