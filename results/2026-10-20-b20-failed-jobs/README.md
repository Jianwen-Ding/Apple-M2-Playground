# B20: how a failed compute job is reported on the M2 Max (2026-10-20)

Blocker B20 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: the kernel never fails the fence.
Shader faults are recovered by firmware and the out-fence signals success (sync-file status 1). The only signs
are firmware timestamps that were never written (end - start = 0) and a host time near 1 ms. Nothing has to be
recreated afterwards.** Hang budget: 3 recorded recoveries (each op54 / jumpout command counted), 0 hangs.

`b20_faults.rs` (local agx_runtime example, not pushed). For each MODE: control on queue A, MODE on queue A,
control on queue A, control on a new queue B in the same VM, control on a new VM, then on a new queue C the MODE
command and a control submitted back to back (no wait in between) with each fence waited separately.
Raw output: `store39.jsonl`, `op54.jsonl`, `jumpout.jsonl` (the evidence rerun; the first runs were identical).

| MODE | What runs | Fence status | Firmware ticks | Host ms | Afterwards (same queue / new queue / new VM / next in-order command) |
| --- | --- | --- | --- | --- | --- |
| `store39` | control storing all 256 words to VA 2^39 (outside the VM) | success | 6,833-7,208 (normal) | 0.13-0.16 | all work, outputs correct |
| `op54` | undecoded opcode 0x54 (`5409` + 3 waits), a recovered fault in the 2026-10-11 scan | **success** | **0** | 0.98-1.12 | all work, outputs correct |
| `jumpout` | `jmp_exec_any pc+1 GiB` into unmapped USC space | **success** | **0** | 1.01-1.60 | all work, outputs correct |

B20 step 1 (from `results/2026-10-20-b25-gpu-telemetry`): `DRM_ASAHI_FEATURE_SOFT_FAULTS` is set, which is why
the store to an unbound VA just disappears.

## What a CUDA runtime must do

- `CUDA_ERROR_ILLEGAL_ADDRESS` cannot be produced from the hardware for out-of-bounds accesses: they are dropped
  (stores) or read 0 (loads, per the uAPI documentation) with a normal completion.
- `CUDA_ERROR_LAUNCH_FAILED` for faulting shaders must come from the **command timestamps**: a completed fence
  whose start and end timestamps are both unwritten (still 0 when zeroed before submission). agx_runtime's
  `error.rs` mapping from a negative fence status never triggers for these cases.
- The queue, other queues of the VM and other VMs keep working after a fault, and the next in-order command on
  the same queue reports its own (successful) status.

## Not covered

- `dmesg` is not readable here (no root), so the kernel's fault log was not captured.
- The firmware timeout (B6) is the remaining failure class; it is expected to be the one that sets a negative status.
