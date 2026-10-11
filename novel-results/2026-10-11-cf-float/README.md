# else_fcmp and while_fcmp match their integer twins for lt, gt and eq (straight-line code)

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Straight-line structures only (no jumps), so no encoding here could loop.

## Claim and scope

Mesa builds `if`/`else`/`while` × `icmp`/`fcmp` from one template (`agx_opcodes.py`:
`0x42 | (int ? 0x10 : 0) | kind << 9`). Running if/else, a jump-free while, and a nested
if/if/else/pop/pop with each float condition (lt, gt, eq) and its integer twin (ult, ugt, ueq) on
lane values 0–31 and two threshold pairs gave **identical per-lane results and identical r0l
snapshots in all 42 cases**. Only 3 of the 8 float condition codes (eq 0, lt 1, gt 2) were
tested, so equivalence is established for those three only; ltn, ge, le, gtn and the unnamed
code 4 were not run in these instructions. `while_*cmp` keeps active the lanes whose condition is true
(nest 1), matching its use as Mesa's loop-continue test.

Not established: NaN operands and the remaining 5 float condition codes in these
instructions (fcmpsel's are mapped in the [sub-op finding](../2026-10-11-subop-spaces/README.md)),
and nest values other than 1.

## Reproducer and evidence

`python3 scripts/run_drm_cf_float.py` (hardware), `python3 scripts/verify_cf_float.py` (offline).
Evidence: `results/2026-10-11-cf-float/cf-float.json.gz`.

## Compiler implications

PTX `setp.{eq,lt,gt}.f32` + `@p bra` structured into if/else/loops can use the float forms directly,
with no integer conversion of the comparison. The other float conditions (ordered/unordered
variants, ge/le) are expected to follow fcmpsel's codes but are unverified in these instructions.
