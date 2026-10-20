# Barrier byte-1 bits are inert: 0x68 has no barrier-ID or count field, and 0x78's byte 1 does not change its 4-group scope

Status: owner-approved unsafe probe (2026-10-20), one device (driver-reported M2 Max G14C B1), direct DRM. **340 submissions
(144 programs), 0 faults, 0 timeouts, fault budget untouched.** This answers the open item "gap bits 8-15: no observable effect with one
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

## Follow-up: closing the gaps

The first pass had blind spots: Mesa's `wait` + `memory_barrier` before the barrier would mask a bit with a
memory-ordering role; there were only 200 trips and 1 submission; only threadgroup memory was used; `0x78` was untested;
and there was no positive control showing the ID test can detect two separate barriers. Follow-up, all at 256 lanes,
16,384 threads, 2,000 trips × 3 submissions:

| Test | Result |
|---|---|
| **No fence before the barrier** (the barrier alone must order memory; 0x68 does this, per the 2026-10-11 study), threadgroup memory: 8 single bits + `68ff` | **0 mismatches for every value**; no-barrier control 212.5M |
| Same, **device memory** | **0 for every value**; no-barrier control 149.9M |
| **Positive control for the ID test**: `7809` on both halves (0x78 synchronizes aligned 4-group blocks, i.e. two separate barriers exactly at the split) | 32.9M mismatches, **only in reading groups 3 and 7**: the split test does detect separated barriers |
| Split ID test without fences, threadgroup and device memory, 9 byte-1 values | 0 mismatches for all: one barrier |
| **0x78 byte-1 sweep**, 8 single bits + `78ff` (each followed by 5 `wait`s in case a value changed the instruction length; simulator-gated on the identical `7809` layout, since the simulator decodes only `7809`), 128 lanes | 0 mismatches for every value (in scope), same time as `7809` within 1% |
| Same at 256 lanes | **every value fails only in reading groups 3 and 7**, the same aligned 4-group scope as `7809` (19.8-31.8M mismatches; the two `7809` controls give 31.8M and 21.1M, so the counts are run-to-run variance) |

(A device-memory run with only 2,048 threads, `g2-prenonememdev`, was insensitive: its no-barrier control showed 0
mismatches. It is retained but not used.)

## Conclusions

- Byte 1 of `0x68` changes neither the participant count, nor the barrier identity, nor the barrier's own memory ordering
  (tested without fences, in threadgroup and device memory). It behaves as padding.
- Byte 1 of `0x78` does not change its scope (aligned 4-SIMD-group blocks) or its cost. Every tested value is the same
  barrier as `7809`.
- A barrier reached from different instruction addresses still synchronizes the whole workgroup.
- For PTX named / counted barriers (`bar.sync id, count`, `bar.arrive`): **no field in `0x68` or `0x78` selects an ID or
  a count.** This does not prove that AGX has no named barriers: another opcode could provide them (the undecoded
  opcodes include 9 dispatch-discarding forms that were not run). Until one is found, ZLUDA should plan to emulate them,
  for example with threadgroup-memory counters, or by supporting only `id = 0` with a full workgroup.

## Not covered

Byte-1 combinations other than single bits and `ff`, workgroups larger than 256 lanes, divergent arrival (some groups
never reaching the barrier: deadlock by design), and other opcodes as possible named-barrier instructions.

## Reproduce

`CONFIRM_GPU_FAULTS=1 python3 -B scripts/run_drm_barrier_bits.py [--size 64|128|256] [--split 0x01,...] [--pre none] [--mem dev]
[--op 0x78] [--total 16384 --trips 2000 --repeats 3] [--extra 0xff]`. Offline: `make verify-barrier-bits` (13 checks against [results/2026-10-20-barrier-bits](../../results/2026-10-20-barrier-bits)).
