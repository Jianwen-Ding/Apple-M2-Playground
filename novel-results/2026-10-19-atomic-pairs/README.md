# Device atomic gap bits are padding: all 10 pairs of the inert singles change nothing

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power.
Owner-approved unsafe session (second item in the loop): the 2026-10-17 single-bit follow-up found
bits 26, 28, 42, 43, 44 inert one at a time on the Mesa `add` encoding (bit 29 zeroes, bit 31
faults). This run flips every pair (C(5,2) = 10) with the same watchdog procedure
(`probe_control_followup.hardware`: pre-saved code, exact recovery control, kernel-log delta,
memory diagnostics). 30 dispatches, 0 faults, hang budget 0/30 throughout, every recovery exact.

## Result

Every pair variant is **bit-identical to its control** (full output + table): the pair flips change
nothing observable, exactly like the singles. No kernel messages in any run.

| Pair | Variant vs control | Recovery |
|---|---|---|
| 26+28, 26+42, 26+43, 26+44, 28+42, 28+43, 28+44, 42+43, 42+44, 43+44 | identical (all words, all guards) | exact x10 |

## Reading

Together with the singles, the u1-u4 gap field (bits 26, 28, 42, 43, 44) is inert singly and in
every pair on the integer-add encoding: it is padding, not a hidden sub-op. No PTX lowering may
rely on it. Not run: triples of these bits (diminishing returns — 15/15 inert so far), pairs
involving bit 29 (zeroing) or 31 (faulting), and threadgroup-atomic bit combinations (separate
sweep; the 19-bit single scan found no float add there).

## Reproduce

`probe_control_followup.case('atomic-gapA+B')` + `F.hardware` per pair (one at a time, stop at
the first halt); `make verify-atomic-pairs` (offline, against
[results/2026-10-19-atomic-pairs](../../results/2026-10-19-atomic-pairs)).
`probe_control_followup.py` now accepts `atomic-gap{bits...}[-op{N}]` with `+`-joined bits.
