# Kernel log of the undecoded-opcode scan — 2026-10-10

The project owner captured the kernel log (`/save/kernel.log`, sha256
`82612fc69fae5180cd47d1bc812d9b4a1805930dcff671d03b40158dfc0733a9`, 5,610 lines)
after the scan in commit `7bfc12c`. The timeouts span 18:04:52–18:11:31 local
(22:04–22:11 UTC), ending one minute before that commit. `gpu-lines.log.gz` keeps
the 5,529 GPU-driver lines. The dropped lines are Docker network setup and one
touchpad firmware message. `summary.json` is produced by
`scripts/summarize_gpu_faults.py` (`make gpu-faults`).

* **286 GPU timeouts** (driver counter 45→330, so about 44 earlier ones fall
  outside the capture). Each was followed by `Halted: 1` and
  "Attempting recovery..." (287 of each). No dead GPU, oops or panic is logged,
  and the GPU later ran normally. This matches the owner's purple flashes and
  stutter: whole-GPU halt and recovery visible to the desktop.
* **73 timeouts carry a fault record, all alike:** `reason: Unmapped`,
  `read: true`, `level: 0x1`, `sideband: 0x51`, unit UL1C(0x0) (unit_code 0x1 70×,
  0x21 2×, 0x11 1×). These are reads from unmapped GPU VAs through a level-1 cache.
* **The addresses fall inside Mesa's user heap,** which starts at 0x11_0000_0000
  (see [direct DRM](../../experiments/baseline/direct-drm-compute.md)):
  0x1100000900 (25×), 0x1100000100 (3×), and junk 0x11_xxxx_xxxx values. The
  most common one is 0x900 bytes into the first user allocation. The remaining
  213 timeouts have no fault record, i.e. the work hung or was killed without an
  MMU fault.
* `vm_slot` takes 45 distinct values. Every scan sample is a fresh process with a new VM.

Limit: scan outputs from that session were not retained (scratch was not
writable then), so individual opcodes cannot be matched to individual timeouts.
A rerun should capture dmesg per candidate, which requires root.
