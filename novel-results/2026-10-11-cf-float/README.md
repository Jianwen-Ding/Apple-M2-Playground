# else_fcmp and while_fcmp behave exactly like their integer twins

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Straight-line structures only (no jumps), so no encoding here could loop.

## Claim and scope

Mesa builds `if`/`else`/`while` × `icmp`/`fcmp` from one template (`agx_opcodes.py`:
`0x42 | (int ? 0x10 : 0) | kind << 9`). Running if/else, a jump-free while, and a nested
if/if/else/pop/pop with each float condition (lt, gt, eq) and its integer twin (ult, ugt, ueq) on
lane values 0–31 and two threshold pairs gave **identical per-lane results and identical r0l
snapshots in all 42 cases**. `while_*cmp` keeps active the lanes whose condition is true
(nest 1), matching its use as Mesa's loop-continue test.

Not established: NaN operands and the remaining float condition codes in these
instructions (fcmpsel's are mapped in the [sub-op finding](../2026-10-11-subop-spaces/README.md)),
and nest values other than 1.

## Reproducer and evidence

`python3 scripts/run_drm_cf_float.py` (hardware), `python3 scripts/verify_cf_float.py` (offline).
Evidence: `results/2026-10-11-cf-float/cf-float.json.gz`.

## Compiler implications

PTX `setp.*.f32` + `@p bra` structured into if/else/loops can use the float forms directly, with
no integer conversion of the comparison.
