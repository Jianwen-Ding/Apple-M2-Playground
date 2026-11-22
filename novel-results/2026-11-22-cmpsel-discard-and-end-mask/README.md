# 2026-11-22: cmpsel `.discard` issue cost, sr58 / sr59 under divergence, ends opcodes vs the exec mask

M2 Max (G14C), direct DRM. Simulator side: AGX-Performance-Simulator `results/2026-11-22-*`.

1. **`.discard` on an icmpsel / fcmpsel select operand** raises SIMD-group issue from 2.03 to 4.84 cycles (32-bit,
   four register sources). Latency is unchanged (2.0). Discard on a compare operand and `.cache` on a select
   operand cost nothing. `.cache` on compare operand B costs +0.2. In the 16-bit forms, discard on a high half is free
   and on a low half it costs 3.55 (base 1.16). Table: [cmpsel-discard.md](cmpsel-discard.md).
2. **sr58 / sr59** are the lane's rank among the active lanes of its SIMD group and that group's active-lane count,
   on all eight masks tested (one lane up to 64 threads). The simulator matches them byte for byte:
   [active-sr.md](active-sr.md).
3. **The ends opcodes** (0x01, 0x0d, ..., 0x7d) executed in a 3-of-4-lane branch end the whole SIMD group. The
   masked-off lanes do not run the stores after the branch (coverage `undecoded/end_*_base_masked`, recorded
   2026-10-16; the simulator ended only the issuing lanes until 2026-11-22). The `stop` instruction is different: it
   ends only the issuing lanes.
