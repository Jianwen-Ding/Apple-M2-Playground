# Device and threadgroup atomics: all 11 Mesa ops exact, with return values and contention

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Only Mesa-emitted encodings were run: no unnamed op value or unaccounted bit reached the GPU,
and no dispatch faulted or timed out (70 dispatches plus controls).

## Claim and scope

**Device `atomic` (0x15, 8 bytes)** and **threadgroup `local_atomic` (0x19, 10-byte long form)**
implement Mesa's op values 0–10 exactly on 32-bit words:
add, sub, xchg, cmpxchg, umin, imin, umax, imax, and, or, xor.

* **Per-lane (no contention).** Each lane operates on its own word with operand X and, for
  cmpxchg, compare Y (half the lanes matching). New values equal the host model for every lane,
  over signed/unsigned edge operands (0, 1, 2^31−1, 2^31, 2^31+1, 2^32−1, alternating bit
  patterns) plus random words. 64 lanes device, 32 lanes threadgroup.
* **Return value.** With Rt = 1 the destination receives the **old** value exactly (preloaded
  0xdeadbeef never survives). Rt = 0 writes no register and still updates memory.
* **Contended word.** All lanes hit one word. For every op the returned values form a valid
  serialization (each lane saw the state left by some ordering of the others) that ends at the
  stored final value.
* **cmpxchg race.** All lanes compare against the initial value: exactly one lane wins and the
  word holds that lane's value (device: lane 32 won; threadgroup: lane 0).
* **Device counter across cores.** 4,096 and 65,536 lanes each add 1 with return: returns are an
  exact permutation of init … init+n−1 and the final value is init+n.
* **cmpxchg operand order** is Mesa's: source register S holds the **new** value, S+1 the
  **compare** value.

Encoding (checked bit-for-bit two ways, applegpu fields and a **Python transcription** of the
Mesa `agx_pack.c` formula). Neither check runs Mesa itself: the "Mesa" side is
`run_drm_atomic.mesa_atomic` (device) and `run_drm_tg_atomic.mesa_local_atomic` (threadgroup),
hand-copied from `agx_pack.c`. Re-reading `agx_pack.c:795-827` (`AGX_OPCODE_ATOMIC`) against
`mesa_atomic`: every field (exact bits 0x15 | 1<<26 | 1<<31 | 5<<44, op<<6, R/A/O split fields,
At<<27, scoreboard<<30, Rt<<47, S<<48, O>>8<<56) matches, with three fixed choices: the index is a
register (Mesa's Ot bit 24 is never set), bit 25 is Mesa's `src[2].abs` (unsigned index), and
bit 45 (`needs_g13x_coherency`) is always clear, which is what Mesa's `agx_gather_device_key`
selects for this single-die G14 (it is set only for multi-cluster G13 or multi-die parts).
`mesa_local_atomic` likewise matches `agx_pack.c:829-857` (`AGX_OPCODE_LOCAL_ATOMIC`) for the one
form used: register base (At = 0), immediate index 0 (Ot = 1), 32-bit destination (Mesa's Rt is
"destination ≥ 32 bits", set here together with Ra when returning). The
offline `verify_atomics.py` re-checks the device encodings against this transcription only; the
threadgroup encodings were checked against `mesa_local_atomic` and applegpu at generation time
(`local_atomic()` raises on disagreement), not in the offline verifier.

```text
device:      0x15 | op<<6 | R<<10 | A<<16 | O<<20 | Ou(25) | 1<<26 | At<<27 | 1<<31
             | 1<<44 | 1<<46 | Rt<<47 | S<<48        (bit 45 = G13X coherency, clear on G14C)
threadgroup: 0x19 | Rt<<8 | R<<9 | 1<<15 | A<<16 | At<<22 | op<<24 | O<<28 | Ot<<34
             | 1<<36 | Ra<<38 | 1<<47 ; bytes 8-9 = S  (index forced to immediate 0: A is a byte address)
```

Not established: op values 11–15, the unaccounted u-bits (deliberately not run: unknown
encodings can hang, and a reboot was not available), 64-bit atomics (Mesa has none),
atomics on uniform-register sources, ordering/visibility guarantees relative to plain loads
and stores in other workgroups, and floating-point atomics.

## Reproducer and evidence

`make test-atomics` (hardware) and `make verify-atomics` (offline, 0 failures).
Runners: `scripts/run_drm_atomic.py`, `scripts/run_drm_tg_atomic.py`.
[Evidence](../../results/2026-10-11-atomics/README.md).

## Relationship to existing knowledge

Mesa (`agx_opcodes.py` ATOMIC_OPC, `agx_pack.c`) defines these encodings, and the earlier
[preshader finding](../2026-10-11-preshader-execution/README.md) validated only device add without
return. applegpu describes both descriptors without hardware tests on Asahi. The per-op results,
return semantics, contention serializability and threadgroup form on G14C are measured here.

## Compiler implications

* PTX `atom`/`red` `.global` and `.shared` `.b32/.u32/.s32` with add, sub, exch, cas, min, max, and, or, xor lower to one instruction each.
  `red` maps to Rt = 0.
* `atom.inc`/`atom.dec` (wrapping) and `.f32` add have no direct op here: use a cmpxchg loop
  until ops 11–15 are characterised.
* Wait on the atomic's scoreboard slot (`wait 0` here) before reading its returned register.
