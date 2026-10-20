# Ordinary r0 writes leave execution unchanged until a mask operation

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**34 variants / 102 dispatches with exact controls, zero faults.**

Ordinary half-word/full-word moves, half-word integer add and immediate moves
can write low r0 without immediately changing the issuing mask. The next
`pop_exec r0l, 1` decrements those written counters and synchronizes execution
accordingly. Thus counter storage and current execution are observably separate
between an ordinary write and a dedicated mask operation.

Begin with all 32 physical lanes active and initialized source depths. Write
r0 through one of these forms, then capture r0 and writer membership before
any IF/pop:

```text
mov r0l, r10l
mov r0, r10
iadd r0l, r10l, 0
mov_imm r0l, d
```

Every lane writes this first snapshot, including lanes whose new r0l is
nonzero. Each copied low value is exact. After pop 1, only lanes initially
written with 0 or 1 execute and read zero; larger counters remain masked.
A bounded drain then reactivates every physical lane for final marker/stop.
An immediate all-lane write of 3 illustrates the distinction: all lanes store
3 before pop, none stores after pop 1, and all write the final marker.

For register-source forms, mixed 0..1, 0..3 and 0..31 inputs use both rotations.
All four forms also use uniform 1,2,3,31 inputs. The no-r0-write control first
copies the same source through an ordinary GPR on all lanes, then constructs
the desired counter state with known IFs for the identical pop/drain trace.
Every whole candidate and control matches independent full-buffer scalar
simulator gates before submission. Initial cases of each form were inspected
before extending patterns. Source and index registers are initialized before
any candidate; no transfer, loop, barrier or invalid address is involved.

Every main/table word, input, snapshot, inactive slot, final marker and guard
is exact. Both known-op controls and every recovery pass, with watchdog/kernel/
memory diagnostics retained. Zero faults or hangs. Simulator 4dd68e9 already
represents this separation and matches all programs; no model change is needed.
The experiment does not characterize zero-count synchronization, writes by
already masked/dead lanes, high r0 state or counter values beyond 31.

```sh
python3 -B scripts/probe_r0_write_mask.py --op mov-imm --maximum 3 --uniform --hardware
make verify-r0-write-mask
```

[Full evidence](../../results/2026-10-20-r0-write-mask/README.md).
