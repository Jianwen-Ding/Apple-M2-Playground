# B21: an executed `trap` (0x0008) is a no-op (2026-10-20)

Blocker B21 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: `trap` does nothing.** Lanes that
execute it continue, every later store lands, other SIMD groups and workgroups are unaffected, the command ends
normally (firmware timestamps written, 7.6-8.6 us), and the next submission works.

`b21.py` uses `probe_variants`: the surrogate program (with the recorded 2-byte no-op 0x18 in place of `trap`)
passed its host oracle in `agx_run`; the variant differs only in that instruction. Each lane stores a marker before
X and another after it, then the harness stores its output. Records: `records.json.gz`. 0 faults; hang budget
unchanged.

| Case | Who executes `trap` | Before markers | After markers | Harness stores | Firmware time |
| --- | --- | --- | --- | --- | --- |
| `trap_all` | all 32 lanes | 32/32 | 32/32 | 32/32 | 7.6 us |
| `trap_odd` | odd lanes, inside Mesa's `if` (partial mask) | 32/32 | 32/32 | 32/32 | 8.1 us |
| `trap_group1` | SIMD group 1 of workgroup 0 (two 64-thread workgroups) | 128/128 | 128/128 | 128/128 | 8.6 us |

A control launch right after also passed.

**For PTX `trap` / `llvm.trap` / CUDA `assert`:** `trap` cannot stop a kernel or fail the launch. Keep the current
software path (`__assertfail` writes the message and a flag word, release fence, then something that really ends the
work, e.g. `stop` for the SIMD group) and report `CUDA_ERROR_ASSERT` from the flag on the host. Ops 11-15 of the device
atomic (B24) and `stop` end a SIMD group; nothing measured so far ends the whole command.
