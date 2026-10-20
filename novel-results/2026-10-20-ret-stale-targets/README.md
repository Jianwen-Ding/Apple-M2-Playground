# RET chooses the cached issuer before changing counter participation

M2 Max G14C B1, direct DRM compute, 2026-10-20. Recorded AC-online is 0;
functional results only. **90 programs / 270 dispatches**, exact controls,
zero faults or hangs.

RET selects the target from the **lowest cached issue-active lane before its
conditional counter update**, even when ordinary writes make execution differ
from zero-counter membership. The earlier [stale-execution matrix](../2026-10-20-ret-stale-exec/README.md)
used uniform targets and could not distinguish these selection rules.

Every lane receives an initialized target at one of three decoded in-program
destinations. A suffix or scattered IF establishes execution; ordinary low-r0
writes update only its issuing lanes without pop0. In a full-mask deep-first
case, lane 0's counter is 3 and lane 1's is 0, with different targets: lane 0
wins. In a full-mask zero-first case, lane 0 becomes masked at RET while lane 1
becomes active, yet lane 0's original target wins. With the first issuer at
lane 5, excluded prefix lanes reactivate through their counter-1 transition,
but their targets do not win. A single original issuer at lane 31 behaves
the same way. This confirms the ordering separately from the counter update.

The matrix has five masks (full/suffix, scattered, first issuer 0/5/31), six
depth patterns (deep/zero/one first and uniform 3/0/1), and three rotations of
the destination labels. Sixty cases differ from zero-counter selection and
66 from after-update participation, including cases where those alternatives
have no eligible lane; 36 reject both alternatives. Three landing checkpoints
also corroborate conditional RET updates and subsequent pop1 synchronization.

Independent controls use IF/jump without ordinary r0 writes or RET. Prefix
stores read back every loaded target, depth and mask flag before divergence.
Each target and fallthrough has its own marker, three conditional snapshots,
12 unrolled pop3 operations, then an all-lane marker and zero-counter check.
The largest input depth is 31; competing valid destinations finish without
loops, barriers, uninitialized sources or invalid addresses. Every actual and
control program first matches complete-buffer scalar oracles in simulator
c7e50f7. Hardware expansion followed exact recovered initial discriminators.

Every main/table word, fallback/landing trace and guard matches independent
offline verification. Original watchdog, firmware timestamps, kernel, memory,
power, boot and recovery metadata are retained. All recovery controls pass;
event counts remain zero. The unchanged simulator reproduces this scope and
all **2,403** original retained control programs exactly. No timing calibration,
counter overflow or new call-target behavior follows from this batch.

```sh
python3 -B scripts/probe_ret_stale_targets.py --first 5 --shape scatter
make verify-ret-stale-targets
```

[Full evidence and aggregate replay](../../results/2026-10-20-ret-stale-targets/README.md).
