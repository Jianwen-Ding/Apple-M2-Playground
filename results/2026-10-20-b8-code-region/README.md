# B8: code region size and in-place code reuse on the M2 Max (2026-10-20)

Blocker B8 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: code and pipeline words can be
rewritten at the same USC address between completed commands without any flush, and one shader can be at least
256 MiB anywhere in the 4 GiB USC range.** 0 faults, 0 hangs; shmem 0 after the runs.

Both probes are local `agx_runtime` examples (copies here; built in a scratch ZLUDA checkout, not pushed). Each
launch waits for completion (`Queue::run_compute`), as agx_runtime's rings only reuse a slot after its fence.

## In-place reuse (`b8_code_reuse.rs`)

The pinned control kernel (stores `mov_imm r2, IMM`) at one USC offset; every iteration writes a new immediate
(0x1111 or 0x2222 in the top half, the iteration number in the low half) **and** different pipeline words
(16 GPR halves + 16 uniform halves on even iterations, 24 + 42 on odd ones), then launches 256 threads.

| Iterations | CDM stream | Wrong words | Stale (previous iteration's value) | Median firmware ticks (ns) |
| --- | --- | --- | --- | --- |
| 1,000 | launch, Mesa barrier (USC cache invalidate), terminate | 0 / 256,000 | 0 | 6,250 |
| 1,000 | launch, terminate (no barrier word) | 0 / 256,000 | 0 | 4,417 |

So the USC cache does not serve stale code across commands even without the barrier word; the barrier costs
about 1.8 us per launch. Not tested: rewriting code that an *in-flight* earlier command still uses (a runtime must
not do that anyway), and back-to-back asynchronous submits on one ring slot (covered by B32's ordering question).

Side finding while writing the test: a kernel whose uniform preload missed its output pointer (u6_u7) stored to
address 0; with soft faults on, the stores vanished and the command completed normally (see B20).

## Size and placement (`b8_big_code.rs`)

Control prefix, `mov_imm r2, 0`, N x `iadd r2, r2.sx, 1`, control suffix; 256 threads must all store N.
The 1 MiB kernel was first run in `agx_run` (same result).

| Shader bytes | Code USC offset | N | Wrong | Firmware time |
| --- | --- | --- | --- | --- |
| 1 MiB | 0x4400 | 131,072 | 0 | 2.57 ms |
| 16 MiB | 0x4400 | 2,097,152 | 0 | 26.9 ms |
| 64 MiB | 0x4400 | 8,388,608 | 0 | 105.8 ms |
| 256 MiB | 0x4400 | 33,554,432 | 0 | 421.5 ms |
| 1 MiB | 0xC0004400 (3 GiB) | 131,072 | 0 | 2.35 ms |

The USC Shader word's 32-bit code address works above 2^31. No per-shader size limit was found below 256 MiB.

## Open

- Start alignments below 64 bytes were not tried (a rounded-down start would execute other bytes); Mesa and
  agx_runtime both use 64.
