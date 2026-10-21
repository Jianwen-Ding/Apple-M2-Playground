# B42: context teardown on the hardware, and two zluda_agx bugs it found (2026-10-21)

Blocker B42 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), ZLUDA master 7a6d979 (real CUDA
contexts, b67e1b2) built locally (not pushed), the checked-in `vectoradd_g14c.o`, battery power. 0 GPU hangs; hang
budget unchanged.

**Result (with the two fixes below): pass.** `b42_teardown.rs` (a local zluda_agx bin), `after-fix-run1000.jsonl`:

| Phase | Result |
| --- | --- |
| 0: 200 launches queued, then `cuCtxSynchronize` and check | correct |
| 1: 1,000 x (cuCtxCreate, cuModuleLoadData, 3 x cuMemAlloc, launch, sync, check, cuCtxDestroy) | 0 wrong, 0 failed, 2.0 ms per cycle; fds 5, RSS 2 MiB, shmem flat |
| 2: 100 x cuCtxDestroy with 200 launches still queued | 0 failed; destroy waits for the work (1.76 ms mean, 2.25 max) |
| 3: 100 x cuDevicePrimaryCtxReset with 200 queued, then a checked launch in the new primary context | 0 failed, 0 wrong |
| System `Shmem` before -> after the process exited | 6,543 -> 6,546 MiB (noise) |

## Bug 1: destroyed contexts leak all their memory in the kernel, past process exit

As shipped, every context lifetime left ~5 MiB of shmem allocated **after the process exited** (system `Shmem` +2,020
MiB and MemAvailable -2,072 MiB after 400 context lifetimes; `before-fix-run200.txt`). That memory stays until reboot
(the 2026-10-16 "55 GB" failure mode of `safe-probes.md` rule 8). This session leaked about 3.1 GiB that way before the
cause was found.

Cause: Rust drops struct fields in declaration order. `agx_runtime::Context` was `{ device, props, vm, stream, allocs }`
and `zluda_agx::Driver` began with `ctx`, so the VM was destroyed first and only then were the queue's rings, the
allocations and the modules' code objects dropped: their `VM_BIND` unbind fails on the dead VM, and a VM destroyed with
objects still bound strands them. Also `Queue`'s drop never unbound its timestamp object (`GEM_BIND_OBJECT` op
UNBIND).

Fix (`zluda-teardown-fix.patch`): VM declared after everything bound in it (`Context { allocs, stream, vm, props,
device }`, `Driver { ..., ctx }` last) and the timestamp object unbound in `Queue::drop`. With it, 1,000 cycles leak
nothing.

## Bug 2: deep launch queues fault without the USC invalidate

With 45 or more launches queued on one stream before a synchronize, some early commands (the 8th to 15th of 200)
complete with both firmware timestamps 0, which `agx_runtime` correctly reports as a fault (EFAULT -> 719,
`CUDA_ERROR_LAUNCH_FAILED`). Flaky from 45 queued, every time from 64. `ZLUDA_AGX_USC_BARRIER=1` (the USC-cache
invalidate after every command, as Mesa emits it) makes 200 queued launches pass every time. The same 200 launches
with each launch's pipeline words in a USC object of its own (`b42_ts.rs`) pass without it.

Cause: zluda_agx stages each launch's pipeline words 64-byte aligned, back to back, in one 256 KiB USC ring, and emits
the invalidate only after a module load. While earlier commands run, the GPU can cache a USC line that also covers a
later launch's not-yet-written pipeline words; that launch then reads stale words. **The invalidate is required
whenever pipeline words are written into USC memory the GPU may already have cached; make it unconditional (Mesa
does), or give every launch's words a fresh line the GPU cannot have fetched.** This corrects B8, which found ring reuse
safe without the barrier with shallow queues.
