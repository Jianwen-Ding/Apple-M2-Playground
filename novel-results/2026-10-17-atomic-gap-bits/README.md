# Device atomic control-bit follow-up

Status: exploratory, one 32-lane integer-add program per bit. Each changes one
bit of `1570a08e10d00c00`, an atomic add returning the old value. Operands mix
small integers, arbitrary words and float bit patterns; lane i addresses table
word i. The complete unmodified program passed agx_run against an independent
integer-add oracle before each hardware variant. Before/after hardware controls
compare every output/table word to that same oracle.

- Bit 26 and bit 28 flips matched the baseline word-for-word.
- Bit 29 flip returned zero in every lane and did not change the input table;
  the harness continuation ran. Its interpretation is not established.
- Bit 31 flip faulted: unmapped UL1C read **0x1000382040**. The known-good
  recovery control passed after two seconds. Budget became 3/30. No claim
  about the semantic meaning of bit 31 follows from that fault.

Records (including exact code, control, inputs, complete stdout/stderr,
readback, kernel-log delta, simulator checks and recovery status) are in
`results/2026-10-17-atomic-gap-bits/`. Failed-dispatch readback is not a valid
semantic oracle. Reproducer: `scripts/probe_control_followup.py atomic-gapBIT`;
default is offline, `--hardware` submits one variant and recovery control.
