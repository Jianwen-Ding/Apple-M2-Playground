# 64-bit atomics: Mesa cannot show a lowering (Honeykrisp reports none), and `atom.add.u64` emulated with two 32-bit adds is exact except for the returned value

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. Straight-line programs, no
loops, no locks, no waiting on a value; only Mesa-named atomic op 0 (add) with return. Gated in the Rust simulator first. 0 faults.

## 1. Mesa's lowering: there is none to decode

* **Honeykrisp (Mesa's Vulkan driver for this GPU) reports `shaderBufferInt64Atomics = 0` and `shaderSharedInt64Atomics = 0`** (also in the
  `VK_KHR_shader_atomic_int64` feature struct) with `shaderInt64 = 1` ([record](../../results/2026-10-18-atom64/honeykrisp-caps.txt),
  query in `tests/vulkan_int64_atomics_caps.c`). A SPIR-V shader using `Int64Atomics` is rejected, so no AGX binary exists to capture.
* Mesa's AGX compiler has no 64-bit atomic path: its `atomic` instruction has only the 11 opcodes ADD, IMIN, UMIN, IMAX, UMAX, AND, OR, XOR,
  XCHG, CMPXCHG and no width field (`agx_pack.c` `AGX_OPCODE_ATOMIC`; `agx_compile.c` `translate_atomic_opcode`).
* The hardware side was already mapped by probing ([atomic-variants finding](../2026-10-17-atomic-variants/README.md)): the only 64-bit forms
  are `red.min.u64` / `red.max.u64` (op 3 with bit 45, bit 46 for max, no return); there is **no** 64-bit add, CAS, exchange or signed form.

## 2. Emulating `atom.add.u64` / `red.add.u64` with two 32-bit atomics

```text
old_lo = atomic_add(lo, v_lo)             (returning)        carry = (old_lo + v_lo) <u v_lo
old_hi = atomic_add(hi, v_hi + carry)     (returning)        old   = (old_hi, old_lo)
```

(7 instructions beyond the two atomics and the loads; the low add must return its old value even when the result is unused, because
the carry depends on it.) 32 runs on hardware, 4,096 lanes each:

| Test | Result |
| --- | --- |
| every lane adds a random 64-bit value to its own word | final value **exact**; returned old value **exact** (8 runs) |
| all lanes add random 64-bit values to one word | final value **exact** (8 runs) |
| all lanes add 2^31 + small (the low word wraps at nearly every add) to one word | final value **exact** (8 runs) |
| all lanes add 1 to one word that starts 256 below a 2^32 boundary (ticket allocation across the carry) | final value **exact**; returned values **never duplicate**, but only **1,556-3,877 of the 4,096 are the expected consecutive numbers**: the others are torn (low word from after the wrap, high word read before the carry was added) |

* **Final values are always exact**: addition commutes, so `red.add.u64` (result unused) and `atom.add.u64` whose result is only
  accumulated are safe to emulate this way.
* **The returned old value is exact only when no other lane touches the word between the two adds.** With no contention it is exact; under
  contention it is torn exactly when the low word wraps. A counter that never crosses a multiple of 2^32 (so the high word is constant)
  gets exact tickets; a ticket allocator that can cross the boundary does not.
* The simulator executes lanes one at a time, so it returns all 4,096 tickets as expected; only hardware shows the tearing.
* Exact `atom.add.u64` with a returned value, `atom.cas.b64`, `atom.exch.b64` and the signed min / max need a lock around the two words or a
  version counter. A lock is a spin loop on a 32-bit CAS (or a bounded retry), which the safe-probe rules forbid running here; it would
  need the owner's approval.

## Reproduce

`scripts/run_drm_atom64.py offline|hardware`; `make verify-atom64` (offline: 6 record checks and a simulator replay of all four modes;
`--no-sim` skips the replay). Records: [results/2026-10-18-atom64](../../results/2026-10-18-atom64).
