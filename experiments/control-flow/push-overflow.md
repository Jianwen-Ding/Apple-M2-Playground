# Bounded counter increment and 16-bit overflow

2026-10-20, before hardware. Wide-counter reads establish unsigned values
through 0xffff, but not increment overflow. Seed initialized half-register
depths, optionally pop0 to synchronize, then execute push_exec n for n=0..3.
Gather every living source's counter and original payload before push,
immediately after, after pop0, and after pop1. The cached mode leaves all
lanes issuing before push despite the ordinary writes. The current simulator
hypothesis increments nonzero counters modulo 65536 and synchronizes execution
to resulting zeros, including overflow zeros. Counter zero stays zero.

Independent controls use initialized expected payloads and simple IF/pop1
masks only: no tested push, ordinary r0 write, wide drain or RET. Actual and
control programs must match scalar full-buffer oracles before submission.
Every byte decodes; all addresses stay in allocated tables. The candidate
ends with a fully unrolled pop3 drain covering the largest original or
expected counter, then an all-lane completion marker. No jump, loop, barrier,
invalid target or uninitialized register is present. The shader is below the
existing 1 MiB harness limit and the prior measured wide drain size.

First inspect low-31 n1 synced/cached cases. Only after exact controls and
recovery, inspect high-boundary n1, then n2/n3. Expand n0/rotations only after
those outcomes are understood. A mismatch stops expansion for analysis.
Retain full partial outputs, timestamps, kernel/memory/power/boot status and
recovery. Faults require an exact recovery control before further submission;
blocked probe process or failed recovery prevents more GPU dispatches.
