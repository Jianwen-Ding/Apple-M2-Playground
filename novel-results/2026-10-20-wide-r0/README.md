# Unsigned execution-counter boundaries through 0xffff

M2 Max G14C B1, direct DRM compute, 2026-10-20. The recorded AC-online state
is **0** throughout this batch; these are functional observations, not timing
measurements. **36 programs / 108 dispatches**, exact controls, zero faults.

Initialized ordinary half-register writes seed each lane's low r0, then
`pop_exec r0l, 0` selects the zero lanes. Immediate-index shuffles directly
read every living source's low counter, including masked sources, before
transfer, at the destination, and after one pop1. A separate bank reads the
unchanged original payload. Original-state jumps and nonempty RET are paired.

| Operation | Observed low-counter behavior |
| --- | --- |
| pop0 after the ordinary write | Numeric values preserved; zero membership becomes execution |
| Nonempty RET | 0 becomes 2, 1 becomes 0, sampled deeper values unchanged |
| pop1 at the destination | Unsigned subtraction with zero saturation |

The staged maxima are 63, 255, 511, 1023, 4095, 16383, 32767, 65534 and
65535. Each vector contains 0/1/2/3, explicit nearby power-of-two boundaries,
and deterministic random values, repeated with a one-lane rotation. This
samples the 16-bit range; it does not enumerate all 65,536 values. The earlier
[consecutive matrix](../2026-10-20-deep-ret-counters/README.md) covers 0..31.

In particular, 0x8000 is read as 32768, not a negative number, and pop1 yields
32767. A masked living source containing 0xffff stays readable, RET preserves
it, and pop1 yields 0xfffe. The final fully unrolled pop3 drain rejoins every
lane. Thus 0xffff is not permanent termination in these programs. No increment
overflow or behavior beyond a half-register's 16-bit storage is established.

Known controls do not seed wide counters, use pop0, or execute RET: initialized
ordinary GPR payloads and simple IF masks independently check source identity,
writer masks, output addresses and guards. Actual and control full programs
must first match scalar full-buffer oracles in simulator c7e50f7. Every target,
fallback and drain entry is a decoded in-program boundary. Competing
fallthrough has its own marker and reaches the bounded drain. There are no
loops, barriers, invalid targets or uninitialized operands.

The largest shader is 143,954 bytes and its drain contains 21,847 pop3
instructions. It fits the existing C harness's dynamically allocated shader
buffer. Widths were advanced only after exact recovered lower-stage outcomes;
the all-ones value followed 65534, and rotations followed the original stages.
Every complete main/table buffer, fallthrough marker and guard matches an
independent verifier. All watchdog, kernel, memory, boot, power and recovery
metadata remain in the original records. No fault or hang occurred.

```sh
python3 -B scripts/probe_wide_r0.py --maximum 65535 --rotate 1 --mode ret
make verify-wide-r0
```

[Evidence and aggregate replay](../../results/2026-10-20-wide-r0/README.md).
The unchanged simulator now replays all **2,313** retained original control
programs exactly. Stale-mask divergent targets and counter-increment overflow
remain separate questions.
