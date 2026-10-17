# Device atomics: bit 45 turns `sub` into a float32 add and `cmpxchg` into 64-bit unsigned min / max; ops 11-15 end the SIMD group

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, 2026-10-17.
Owner-approved probes of encodings Mesa never emits: 54 dispatch pairs, **0 faults, 0 hang-budget events**, kernel log
clean, a control dispatch passed after every step.

## Method: the surroundings are simulated, the variant is not

The simulator cannot execute an unknown encoding, but it can execute everything around it. Each probe
(AGX-Performance-Simulator `scripts/probe_variants.py`) is `prefix + X + suffix`:

1. X is either a **surrogate** (a Mesa encoding that `agx_run` models and the GPU has run) or the **variant** under test.
   The variant may differ from the surrogate only inside an allowed bit mask: the op field (bits 6-9) or bits 45-46.
2. The surrogate program must pass the decode gate, run to its end in `agx_run` with the harness layout, and equal a
   host oracle for its output and memory (addresses in range, every store where expected, no loop).
3. Only then does the variant program run on the GPU, twice, through `tests/drm_compute.c` (whole program, final
   `stop` checked, faults charged to the hang budget). The first fault would stop the batch.

The probes are in AGX-Performance-Simulator `scripts/probe_atomics.py` (families A-I below). The models are fitted
offline.

## Encoding

The device `atomic` (0x15, 8 bytes) as Mesa packs it (`agx_pack.c`), with the gap field applegpu calls `u5`:

```text
0x15 | op<<6 | R<<10 | A<<16 | O<<20 | Ou(25) | 1<<26 | At<<27 | 1<<31 | 1<<44 | b45<<45 | b46<<46 | Rt<<47 | S<<48
Mesa on G14: b45 = 0 (its "needs_g13x_coherency" bit), b46 = 1
```

| op | b45 = 0 (b46 either) | b45 = 1, b46 = 0 | b45 = 1, b46 = 1 |
|---|---|---|---|
| 0 add, 2 xchg, 4-10 min / max / and / or / xor | Mesa's 32-bit op | same 32-bit op | same 32-bit op |
| **1 sub** | integer sub | **float32 add** | **float32 add** |
| **3 cmpxchg** | 32-bit compare-and-swap (new = S, compare = S+1) | **64-bit unsigned min** | **64-bit unsigned max** |
| **11-15** | **no memory effect; ends the SIMD group** (b45 / b46 at Mesa's values) | not run | not run |

Bit 46 alone changes nothing (all 11 ops, 33 variants).

## Results

### Float32 atomic add (op 1 + bit 45), the PTX `atom.add.f32` operation

- **Semantics:** `mem = old + S`, with the old word returned when Rt = 1.
  - All 2,048 edge and rounding pairs (40 × 40 edge words: ±0, denormals, FLT_MIN neighbours, ties, FLT_MAX, ±inf, NaN
    payloads, plus 448 random pairs with close exponents) match **round to nearest even, with denormal inputs and
    results flushed to sign-preserving zero**.
  - The denormal-preserving model is contradicted on 109 lanes.
  - Every NaN result is the canonical `0x7fc00000`, including signalling and payload NaN inputs, and inf + −inf.
- **This is exactly PTX's definition of `atom.add.f32`.** PTX specifies that it rounds to nearest even and flushes
  subnormal inputs and results to sign-preserving zero, so one instruction implements it.
- **Atomic under contention:**
  - 1,024 lanes adding 1.0 to one word end at exactly 1024.0, and their returns are exactly {0.0 … 1023.0}.
  - With mixed addends, the 1,024 returns form a single serial chain from the initial value to the final one.
  - The order varies between runs, as expected.

### 64-bit unsigned min / max (op 3 + bit 45; bit 46 selects max)

- **Operation:** on the 64-bit word at **base + 4 × index**. The index stays in 32-bit words, so a 64-bit element k
  needs index 2k. The source is the register pair S.
- **Unsigned:** 13 of the 32 lanes per run would differ under a signed order, and they follow the unsigned result.
- **Return value:** with Rt = 0 no register is written. **With Rt = 1 the destination receives 1 if memory changed
  and 0 otherwise, not the old value** (32/32 lanes, min and max).
- **Matches the published claim:** "M2 adds a non-returning u64 min / max" (Apple GPU family 8) is this
  encoding, and applegpu's note on `u5` (1 = umin64, 3 = umax64) holds on G14C.

### Ops 11-15

- **No memory effect, and execution stops.**
  - A store placed before the op lands; nothing after it runs, not even a store after re-enabling every lane with
    `mov_imm r0l, 0`.
  - The dispatch completes normally (firmware timestamps written, no fault).
- **Scope:** two workgroups × two SIMD groups, with op 11 only in odd lanes of each workgroup's second SIMD group.
  - Inside Mesa's `if` (`jmp_exec_none` skips empty groups): the groups that skip it finish, and **the issuing group
    ends, including its inactive lanes**.
  - Without the skip: every group issues it with an empty mask, and all stop.
- This is the behaviour of the 16 "ends" opcodes (`2026-10-11-opcode-descriptions`). None of ops 11-15 is a float
  min / max, inc / dec or any other atomic.

## Compiler implications (PTX → AGX)

| PTX | AGX |
|---|---|
| `atom.global.add.f32` | one `atomic` op 1 + bit 45, Rt = 1. **No CAS loop needed** (the 2026-10-11 finding assumed one) |
| `red.global.add.f32` | op 1 + bit 45 with Rt = 0: **not yet run**, expected to work like the integer ops |
| `red.global.min/max.u64` | op 3 + bit 45 (+ bit 46 for max), Rt = 0, index = 2 × element |
| `atom.global.min/max.u64` (returns old) | **no direct form**: Rt = 1 returns only a "changed" flag |
| `atom.*.s64` min / max, `.add.u64`, `.cas.b64`, `.exch.b64`, `.add.f64`, `.min/max.f32` | **no encoding** found in the op field or bits 45-46 (all 11 ops × 3 bit patterns, ops 11-15) |
| anything | never emit ops 11-15 (they silently end the SIMD group) |

- The missing 64-bit forms still need emulation, for example a lock word built from a 32-bit CAS, or splitting
  monotonic counters.
- `atom.min.u64` with a return value can sometimes be rebuilt: the flag says whether this lane won, and if it lost,
  the memory value is at most its source. That is enough for the common "first-wins" uses, but not for a general old
  value.

## Relationship to existing knowledge

- **Mesa** sets bit 45 only for multi-cluster G13 and multi-die parts (`agx_gather_device_key`), described as a
  coherency quirk.
  - On G14C that bit selects float add / 64-bit min-max for `sub` / `cmpxchg` and is ignored elsewhere.
  - Whether Mesa's integer `sub` and `cmpxchg` behave differently on G13X is **open** (no G13X device here).
- **applegpu**'s `u5` note (with cmpxchg: 1 = umin64, 3 = umax64) is confirmed. Float add, the return flag and ops
  11-15 are new.
- **Metal** exposes `atomic<float>` fetch-add and Apple 8 `ulong` min / max. These are presumably the instructions
  behind them (not checked against Metal's compiler output).

## Open

- Float add with Rt = 0 (`red.add.f32`), and its throughput under contention against the integer rate (0.86 ns per
  lane-operation, `2026-10-16-atomic-contention`).
- The "changed" flag of umin64 / umax64 when the source equals memory (no tested lane had equal values).
- 64-bit min / max under contention, and with a register base.
- The threadgroup atomic (`local_atomic`, 0x19) has its own unexplained bits (u1, u3, u4, u5). A float add there is
  untested.
- The remaining gap bits u1-u4 (bits 26, 28-29, 31, 42-44) of the device atomic.

## Reproducer and evidence

- `make verify-atomic-variants` (offline): 22 checks, with the models re-implemented independently of the probe.
- `make atomic-variants CONFIRM_GPU_FAULTS=1` (hardware): every family, each probe gated in `agx_run` first.
- Evidence is in [results/2026-10-17-atomic-variants](../../results/2026-10-17-atomic-variants): all 54 records, with
  code, input and output tables, and snapshots of the probe and harness.
