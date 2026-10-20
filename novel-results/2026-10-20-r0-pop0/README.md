# Zero-count pop synchronizes execution after ordinary r0 writes

M2 Max G14C B1, direct DRM compute, AC power, 2026-10-20.
**34 variants / 102 dispatches with exact controls, zero faults.**

`pop_exec r0l, 0` is an execution synchronization operation, not a skipped
no-op. After an ordinary r0 write leaves execution unchanged, a zero-count pop
lets only written zero-counter lanes execute. Written ones remain masked,
unlike the [pop-1 result](../2026-10-20-r0-write-mask/README.md). A uniform
nonzero ordinary write leaves all lanes active until pop 0, then none writes
the following checkpoint. A later bounded drain reactivates all lanes.

The matrix repeats all four previously measured write forms: half/full moves,
half integer add and uniform immediate move. Register-source cases include
mixed 0..1, 0..3, 0..31 depths with both rotations; all forms also use uniform
1,2,3,31. Every lane's immediate post-write r0 copy matches its input, while
the post-pop0 plane contains zero only for original zero-counter lanes.
This directly separates execution synchronization from the counter write.

Recovery controls do **not** contain pop 0. They copy the input through an
ordinary GPR, construct the known counter/mask state with IFs, then execute
waits before the same snapshot/drain. This avoids assuming the new behavior
in a known-good control. Both complete programs first match scalar simulator
gates. Initial mixed-register and uniform-immediate cases were inspected
before extending the matrix. Every source/index is initialized, and no
transfer, loop, barrier or invalid memory occurs.

Every main/table word, input, masked slot, final marker and guard is exact.
All before/after controls and recovery checks pass; watchdog/kernel/memory
diagnostics are retained. Zero faults or hangs. Simulator 4dd68e9 already
matches every program. Nonzero masked numeric values after pop0 are not read
directly here; the observation establishes zero-membership synchronization.
Larger counters, already-masked ordinary writes and other mask operations
remain follow-ups. No timing or uninitialized-data claim is made.

```sh
python3 -B scripts/probe_r0_pop0.py --op mov-imm --maximum 3 --uniform --hardware
make verify-r0-pop0
```

[Full evidence](../../results/2026-10-20-r0-pop0/README.md).
