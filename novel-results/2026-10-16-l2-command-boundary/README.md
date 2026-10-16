# Compute command boundaries in *another* process evict the GPU-wide L2

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power.

## Claim and scope

**Test:**
- A 64 KiB random pointer chase (L2-resident, one SIMD group, 80,000 hops per dispatch, 16 dispatches) ran while a
  second process submitted a 64-lane delay kernel in different patterns.
- Every kernel passed the simulator's `agx_run` oracle first, and every readback was exact.

| Background (other process) | Command boundaries | GPU busy | Chase ns per hop (median) |
|---|---|---|---|
| none | — | — | **96.0** |
| a: 64 × 0.13 ms commands per SUBMIT, back to back | one every ~0.13 ms | ~100% | **283** (min 200) |
| b: one 0.13 ms command, then 5 ms idle | one every ~5 ms | ~3% | 101.4 |
| c: 6.3 ms commands, back to back | one every 6.3 ms | ~100% | 99.2 |

- **The slowdown follows the rate of command boundaries, not the background load.** Background c keeps 2 SIMD
  groups busy all the time with no effect, while a triples L2-resident latency.
- Each compute command start or end, in any queue of any process, invalidates or flushes the L2 shared by all
  cores.
- The likely mechanism is the CDM barrier that ends every command: Mesa's `unk0..19` bits, including cache
  invalidates (`docs/drm-interface.md` §3). The individual bits were not varied, and they never will be by hand.

**Consequences found in this session:**
- The first version of `scripts/clock_keeper.py` used background a. Memory measurements taken under it were
  inflated: the first cache-line run and the first TLB sweep. Both were redone. ALU-only measurements (the 0x18
  costs, ending opcodes) are unaffected.
- The keeper now uses 6.3 ms commands. It holds the top clock (L1 chase 40.3 ns) and leaves L2 within ~3%.

**Not established:**
- whether L1 is also invalidated (an L1-resident chase showed no effect under a);
- whether render commands do the same;
- whether the effect applies within one queue between its own commands (likely, since every command ends with the
  same barrier).

## Reproducer and evidence

- `make verify-l2-command-boundary`: offline, 12 checks.
- [Evidence](../../results/2026-10-16-l2-command-boundary/): the five chase records, the background kernels and
  harness snapshots.

## Runtime implications (CUDA)

- A stream of many short kernels destroys L2 locality for *every* concurrently running kernel on the GPU.
- Kernel fusion and fewer, longer launches matter more here than on NVIDIA.
- Benchmarks must not run next to a short-kernel load.
