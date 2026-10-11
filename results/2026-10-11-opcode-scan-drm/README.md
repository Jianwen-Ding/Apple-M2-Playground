# Direct-DRM undecoded-opcode classification — 2026-10-11 (STOPPED: device unresponsive after 0x5c)

Owner-approved, `CONFIRM_GPU_FAULTS=1`. `scripts/run_drm_opcode_scan.py` ran each
of the 59 opcodes applegpu cannot decode (minus excluded 0x6e) as a two-byte
`op | Dt=2 | D=r2` form in the pinned control's main, one candidate per
submission, direct DRM (no Mesa). 40 of 59 were classified before the scan
stopped itself.

| File | Contents |
| --- | --- |
| `validate-0x18.json` | Single-candidate sanity check (0x18, known no-op from the earlier Vulkan scan) before the full run |
| `scan-1.json` | Full scan record: 40 classified, stopped after 0x5c |
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

## Status

The scan is **not resumed** pending the owner confirming the device is usable
again (a reboot may be needed; this session cannot check or perform one). No
further GPU submissions were attempted after the three failed recovery checks.
