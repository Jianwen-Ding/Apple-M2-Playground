# Direct-DRM undecoded-opcode classification — 2026-10-11 (56 of 59 classified; 0x5c/0x64/0x74 not rerun)

Owner-approved, `CONFIRM_GPU_FAULTS=1`. `scripts/run_drm_opcode_scan.py` ran each
of the 59 opcodes applegpu cannot decode (minus excluded 0x6e) as a two-byte
`op | Dt=2 | D=r2` form in the pinned control's main, one candidate per
submission, direct DRM (no Mesa). 40 of 59 were classified before the scan
stopped itself.

| File | Contents |
| --- | --- |
| `validate-0x18.json` | Single-candidate sanity check (0x18, known no-op from the earlier Vulkan scan) before the full run |
| `scan-1.json` | Full scan record: 40 classified, stopped after 0x5c |
| `scan-2.json` | Resume after reboot: the 16 opcodes never executed by any earlier scan, 0 faults |
| `post-0x5c-control-fails.json` | Unchanged-control dispatch after 0x5c: SUBMIT itself failed (syncobj wait timed out, errno 62/ETIME, 3.0 s) |

## Result

* **24 no-ops** (r2 unchanged): 0x3, 0x7, 0xb, 0xf, 0x13, 0x17, 0x18, 0x1b, 0x1f,
  0x23, 0x27, 0x2b, 0x2f, 0x33, 0x37, 0x3b, 0x3f, 0x43, 0x47, 0x4b, 0x4f, 0x53,
  0x57, 0x5b. 0x18 matches the earlier Vulkan-path classification.
* **9 end the thread/group** (the suffix never stores): 0x1, 0xd, 0x1d, 0x2c,
  0x2d, 0x3c, 0x3d, 0x4d, 0x50. This is a new, finer result than the earlier
  Vulkan scan, which only reported "discards every store of the whole
  dispatch" for a different candidate set; these nine are measured as ending
  execution without a whole-GPU fault (firmware timestamps present, guards intact,
  host time normal).
* **7 fault/hang, recovered**: 0x6, 0x24, 0x34, 0x44, 0x46, 0x54 (matches the
  nine `CLASS_C` opcodes from the 2026-10-04 Vulkan scan, minus 0x64 and 0x74,
  not yet reached here). Host time for these ranged 1.1-752.9 ms; three (0x6,
  0x24, 0x34) show the same ~502.6 ms signature as the helper-program hangs.
* **0x5c (the 8th CLASS_C-adjacent candidate here) left the device unresponsive
  to further SUBMIT calls.** The candidate's own dispatch took 3.02 s (hit the
  harness's own 3 s syncobj-wait ceiling, i.e. did not recover inside it). The
  scanner's mandatory post-fault control dispatch then failed outright: three
  manual retries of a plain control dispatch all failed identically, errno 62
  (ETIME) on the syncobj wait. This is a stronger failure than the ~0.5-0.75 s
  recoveries seen for 0x6/0x24/0x34/0x46/0x54, and matches the documented Asahi
  risk that "repeated firmware faults can require a reboot."
* **18 opcodes were never reached**: 0x5d, 0x5f, 0x60, 0x63, 0x64, 0x67, 0x6b,
  0x6c, 0x6d, 0x70, 0x73, 0x74, 0x77, 0x78, 0x7b, 0x7c, 0x7d, 0x7f.

## Resume after reboot (scan-2)

The machine was rebooted after the 0x5c wedge. The unchanged preload control passed
first, so the device was healthy again. On the owner's instruction, only opcodes that had
**never crashed in any earlier scan** were run. That skipped 0x5c (direct-DRM wedge)
and 0x64/0x74 (whole-dispatch faults in the 2026-10-04 Vulkan scan). The run used
`--max-faults 1`, so it would have stopped at the first new fault:

```sh
CONFIRM_GPU_FAULTS=1 python3 -B scripts/run_drm_opcode_scan.py \
  --opcodes 0x5d,0x5f,0x60,0x63,0x67,0x6b,0x6c,0x6d,0x70,0x73,0x77,0x78,0x7b,0x7c,0x7d,0x7f \
  --max-faults 1 --pause 2
```

All 16 completed normally. Firmware time was 6.5-8.2 µs, host time 0.2-0.6 ms, and
every guard word was intact. **0 faults.**

* **9 no-ops:** 0x5f, 0x63, 0x67, 0x6b, 0x73, 0x77, 0x78, 0x7b, 0x7f
* **7 end the thread/group:** 0x5d, 0x60, 0x6c, 0x6d, 0x70, 0x7c, 0x7d

The kernel log in the container shows no GPU-driver timeout or recovery lines. It may
be a boot-time snapshot, though (live `dmesg` needs root), so this is supporting
evidence only.

## Combined classification (scan-1 + scan-2, two-byte `op | Dt=2 | D=r2` form)

| Class | Opcodes |
| --- | --- |
| no-op (33) | the 31 undecoded opcodes with low bits `0b11` (0x03, 0x07, …, 0x7f; 0x6f is decoded by applegpu and was not scanned), plus 0x18 and 0x78 |
| ends thread/group (16) | 0x01, 0x0d, 0x1d, 0x2c, 0x2d, 0x3c, 0x3d, 0x4d, 0x50, 0x5d, 0x60, 0x6c, 0x6d, 0x70, 0x7c, 0x7d |
| fault, recovered (6) | 0x06, 0x24, 0x34, 0x44, 0x46, 0x54 |
| fault, device wedged until reboot (1) | 0x5c |
| not run (3) | 0x64, 0x74 (Vulkan-scan faulters, skipped on purpose); 0x6e (excluded, LeftoverLocals class) |

Patterns, observed with this one operand encoding only:
* All 31 undecoded opcodes with low two bits `0b11` are inert. Among the other
  undecoded opcodes, only 0x18 and 0x78 are. (Corrected: an earlier version said
  32 low-`0b11` opcodes plus 0x18 and missed 0x78. 0x6f is decoded, so it was not in the scan.)
* The `…1100`/`…1101` opcodes (0x2c/0x2d, 0x3c/0x3d, 0x6c/0x6d, 0x7c/0x7d, and the
  `…1101` members 0x0d/0x1d/0x4d/0x5d) end execution cleanly. 0x5c is the exception
  in that column, and it is the only opcode that wedged the device.
* Every fault so far has an opcode ≡ 0, 4 or 6 (mod 8) in the 0x04-0x74 range.
  Other operand encodings (wider forms, other Dt values) were not tested.

## Follow-up

Each non-faulting opcode is described in
[novel-results/2026-10-11-opcode-descriptions](../../novel-results/2026-10-11-opcode-descriptions/README.md).
The scan's "no-op" class is really two classes: 31 **6-byte** no-ops (this scan's 2-byte
form swallowed 4 bytes of `wait` padding) and the 2-byte control ops 0x18/0x78. "Ends"
means the whole SIMD group ends, whatever the exec mask.

## Status

Classification is complete except for the three deliberately skipped opcodes. **Do
not rerun 0x5c without the owner's agreement:** on direct DRM it left SUBMIT failing
(ETIME) until a reboot. 0x64/0x74 are expected to fault and are skipped for the same
reason.
