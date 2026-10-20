# threadgroup_barrier 0x68: byte-1 bits (gap bits 8-15) are inert with several SIMD groups; no barrier-ID field

Status: owner-approved unsafe probe (2026-10-20), one device (driver-reported M2 Max G14C B1), direct DRM. **46 submissions,
0 faults, 0 timeouts, fault budget untouched.** This answers the open item "gap bits 8-15: no observable effect with one
SIMD group; scope effects untested" ([mem-control gap bits](../2026-10-11-mem-control-gap-bits/README.md)), and whether
PTX named barriers (`bar.sync id, count`) could map onto a field of `0x68`.

## Test

The message-passing stress loop of [0x68 vs 0x78](../2026-10-11-barrier-0x68-vs-0x78/README.md)
(`scripts/run_drm_barrier_stress.py`): every lane writes 8 values to threadgroup memory, then Mesa's sequence (`wait`,
`memory_barrier`) and the candidate barrier, then it reads another SIMD group's values and counts mismatches, then a
second barrier; 200 trips. Every group executes every barrier with uniform control flow. Each body is simulator-checked
first (`scripts/run_drm_barrier_bits.py`).

| Test | Result |
|---|---|
| Uniform: all groups use `68 XX`, each single bit of byte 1, at 64 / 128 / 256 lanes (2 / 4 / 8 SIMD groups) | **0 mismatches for every bit at every size**, the same as `6800`. The no-barrier control fails (17,813-1,494,543 mismatches). Same time as `6800` within 1% |
| Split (barrier-ID test, 256 lanes): groups 0-3 execute `6800`, groups 4-7 `68 XX` (8 single bits and `68ff`), through a group-uniform `if` / `else` | **0 mismatches and no hang for every value**: all 8 groups still meet at one barrier. A separate barrier per ID would leave cross-half readers unsynchronized; an ID barrier waiting for the whole workgroup would hang |
| Control: the split with `6800` on both sides (barrier reached from two code addresses) | 0 mismatches: one barrier regardless of which instruction instance is executed |

## Conclusions

- Byte 1 of `0x68` changes neither the participant count nor the barrier identity. It behaves as padding, as it did with one
  SIMD group.
- A barrier reached from different instruction addresses still synchronizes the whole workgroup.
- **PTX named / counted barriers (`bar.sync id, count`, `bar.arrive`) have no hardware field in `0x68`.** ZLUDA must emulate
  them (for example with threadgroup-memory counters and spinning, or by restricting to `id = 0` with a full workgroup).
  The 4-SIMD-group `0x78` form remains the only other barrier scope found.

## Not covered

Bit combinations other than `68ff`, workgroups larger than 256 lanes, and divergent arrival (some groups never reaching the
barrier: deadlock by design).

## Reproduce

`CONFIRM_GPU_FAULTS=1 python3 -B scripts/run_drm_barrier_bits.py [--size 64|128|256] [--split 0x01,...]`. Offline:
`make verify-barrier-bits` (6 checks against [results/2026-10-20-barrier-bits](../../results/2026-10-20-barrier-bits)).
