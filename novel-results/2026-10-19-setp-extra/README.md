# Non-ftz setp is complete: NaN-accepting variants and float-result set are exact; fp16 compares map directly

Status: confirmed on one device (driver-reported M2 Max G14C B1; user confirms board is a MacBook M2 Max),
direct DRM, compute stage, AC power. Straight-line programs, no loops, only encodings already recorded
safe. Decode-gated at construction and replayed in the Rust simulator (`agx_run`) against the IEEE host
model before submission; 0 GPU faults or timeouts (hang budget untouched).
This closes the correctness half of the safe-01 open part in
[remaining-work](../../docs/remaining-work.md) (row 2), extending the
[fcmp finding](../2026-10-18-fcmp/README.md).

## 1. NaN-accepting setp variants and float-result set (fix-up extension)

`scripts/run_drm_fcmp_fixup.py --extra` appends to the proven integer-key fix-up program:
- `.u` variants from the same raw relations: `neu = !eq_raw | nan`, `equ = eq_raw | nan`,
  `ltu/leu/gtu/geu = raw | nan`, `num = !nan`, `nan = nan mask` (one `icmpsel` + one `or` each);
- float-result `set`: `rel ? 0x3f800000 : 0` via `icmpsel ueq` with the 1.0 word loaded from
  the table (the `mov_imm` helper form only encodes destinations r0-r31; see harness notes below).

**Result: all 20 outputs exact on all 2,304 edge-value pairs in all 3 runs**
(`make verify-fcmp-extra`; [evidence](../../results/2026-10-19-fcmp-extra)).
The 7 base outputs reproduce the 2026-10-18 exactness unchanged.

PTX mapping for default (non-`.ftz`) `setp` / `set` / `min` / `max`:
- `.eq/.lt/.gt/.le/.ge` + `.min/.max`: the published integer-key fix-up (unchanged).
- `.neu/.equ/.ltu/.leu/.gtu/.geu`: same keys, force-true on NaN (the `or r24` tail).
- `.num` / `.nan`: the NaN mask (possibly inverted).
- `set` (float result): select the 1.0/0.0 words with the predicate.
- `.ftz` forms map directly to `fcmpsel` (subnormals already read as zero).

## 2. fp16 compares need no fix-up

`scripts/run_drm_fcmp16.py`: `fcmpsel CC, r20l, r6l, r7l, r21l, r22l` (the recorded-safe half
form, r20 pre-zeroed) over 31 x 31 = 961 half-edge pairs (subnormal halves 0x1..0x3ff and
negatives, smallest normals, near-1/2, max finite, +-inf, seven NaNs), all seven conditions,
host oracle from exact `struct '<e'` conversion with bit-pattern NaN checks.

**Result: 961/961 exact vs IEEE in all 7 conditions x 2 repeats, inputs intact**
(`make verify-fcmp16`; [evidence](../../results/2026-10-19-fcmp16)).
Subnormal halves compare exactly (no flushing), NaN gives false except the `ltn`/`gtn`
second-operand-NaN-true rule, same as fp32. `setp.f16` maps directly to `fcmpsel`.

## Still open in row 2 (not hardware)

- The cycle cost of the fix-up (~15-16 integer instructions plus 4 hoisted constant moves;
  unmeasured on hardware).
- Compiler skip conditions (prove an operand normal or `.ftz`-produced, then use `fcmpsel`
  directly): analysis only, needs the backend.

## Harness notes (also added to failed-approaches)

- `chains.mov_imm` 6-byte form only encodes destinations r0-r31: `mov_imm(37, ...)` assembles
  bytes that re-decode as an 8-byte instruction (length desync). High registers are fine as
  `icmpsel`/`load`/`store` operands (used to r38 here); materialise high-reg constants with a
  table load instead.
- The `isnan` lambda (`... and b & 0x7fffff`) returns a payload int, not a bool: it is safe in
  `if` conditions but `int(isnan(a) or isnan(b))` keeps the payload. Normalise with `bool()`
  in oracles (this made the `nan` oracle wrong before the hardware run; the hardware was right).

## Reproduce

`scripts/run_drm_fcmp_fixup.py hardware --extra --repeats 3` (3 dispatches; `offline --extra`
replays all 20 outputs in `agx_run` against the IEEE host model first),
`scripts/run_drm_fcmp16.py hardware --repeats 2` (14 dispatches),
`make verify-fcmp-extra verify-fcmp16` (offline, against the retained records).
Every instruction form used was already recorded safe; all programs are straight-line with
`stop` terminators and were gated in the Rust simulator before submission.
