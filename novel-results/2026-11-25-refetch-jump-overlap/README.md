# A refetched jump target's fetch overlaps the straight run before the jump; an idle `wait` does not stop the code stream

Status: one device (M2 Max G14C), 2026-11-25, AC power. Our own probe (AGX-Performance-Simulator
`scripts/probe_fetch_groups.py SKIP=R,D`), using only forms it and the jump probes ran before (iadd, jmp_exec_any,
wait, stop, while_icmp). Nothing was disassembled or decompiled. No faults.

There is a loop over about 48 KB of executed straight code, beyond the 12 KiB i-cache. After every R executed lines, a
`jmp_exec_any` jumps over D lines of `stop` filler. Each warm trip refetches everything.

| R, D | warm trip, us (hw) | per jump beyond a streamed line |
|---|---|---|
| no jumps | 23.4 | - |
| 1, 8 (every line is a target) | 106.5 | ~107 ns (~138 ns per line) |
| 4, 4 / 4, 32 | 31.6 | ~15 ns |
| 16, 16 | 24.1 | ~0 |

- The target's fetch starts long before the jump issues: it overlaps the run of lines before it. Only isolated
  targets (1-line runs) pay the ~140 ns refetch latency.
- Jump distance (4 vs 32 lines) does not matter for warm refetches.
- `wait 0` with nothing outstanding (the probe's padding) does not stop the stream. A wait on a pending load does
  (2026-11-10 code-refetch-stream).
- Compiler: in code beyond the i-cache, taken branches are nearly free when they end runs of 4 or more lines, but
  1-line blocks cost ~140 ns each.
