#!/usr/bin/env python3
"""Threadgroup atomic opcodes 11..15 and unmeasured control-bit changes.

One SIMD group. Full 2 KiB scratch fill and one barrier precede the unknown
instruction; no barrier follows it. Complete baseline is simulator/oracle gated.
Each hardware run records controls, faults, recovery and memory diagnostics.
"""
import argparse
import json
from pathlib import Path
import probe_control_followup as F

P = F.P
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'results/2026-10-17-tg-atomic-followup'
OPS = [f'tg-op{i}' for i in range(11, 16)]
MASKS = [f'tg-op{i}-{mask}' for i in range(11, 16) for mask in ('odd', 'empty')]
BITS = ['tg-sub-bit36', 'tg-sub-bit47', 'tg-cas-bit36', 'tg-cas-bit40', 'tg-cas-bit47']
EXTRA = [f'tg-{op}-{bits}' for op in ('sub', 'cas')
         for bits in ('bit34', 'bits45-46', 'bits36-47')]
SKIPS = ['tg-op11-empty-skip']


def case(name):
    assert name in OPS + MASKS + BITS + EXTRA + SKIPS, name
    P.cov.install()
    import probe_atomics as A
    from run_drm_atomic import apply, OPS as NAMED
    e, mov, st = P.RS.e, P.RS.mov, P.RS.agx_loop.store
    base = A.probes_t2()[0]
    op = 3 if name.startswith('tg-cas') else 1
    table = base.table + [0] * 32
    if op == 3:
        for i in range(0, 32, 2):
            table[128+i] = table[i]
    pre = base.prefix
    # These addresses are prepared before the unknown operation.
    for r, off in ((20, 192), (21, 224), (23, 768)):
        pre += mov(27, off) + e(f'iadd r{r}, r1, r27')
    pre += mov(26, 0xfeed0001) + st(26, 8, 20) + e('wait 0')
    active = [True] * 32
    if name in MASKS + SKIPS:
        odd = name.endswith('-odd')
        active = [bool(i & 1) if odd else False for i in range(32)]
        pre += mov(27, 1 if odd else 32) + e('and r25, r1, r27')
        pre += e('if_icmp r0l, ueq, r25, r27, 1')
        if name in SKIPS:
            pre += P.RS.jnone(6 + 10)
    surrogate = A.mesa_local_atomic(op, 10, 44, 12, True)
    if name in OPS + MASKS + SKIPS:
        value = int(name.removeprefix('tg-op').split('-')[0])
        allowed = 0xf << 24
        variant = (surrogate & ~allowed) | (value << 24)
    else:
        bits = [int(v) for v in name.split('bit')[1].removeprefix('s').split('-')]
        allowed = sum(1 << bit for bit in bits)
        variant = surrogate ^ allowed
    assert ((surrogate ^ variant) & ~allowed) == 0
    sur, var = (v.to_bytes(10, 'little') for v in (surrogate, variant))
    info = P.cov.ASMB.info(var)
    assert info and info[0] == 'threadgroup_atomic' and info[1] == 10
    # No barrier after unknown op: it may end the group or mask the lanes.
    assert base.suffix[:4] == e('wait 0') + bytes.fromhex('6800')
    suf = e('wait 0') + mov(26, 0xcafe0001) + st(26, 8, 21) + e('wait 0')
    suf += e('pop_exec r0l, 3') + mov(26, 0xcafe0002) + st(26, 8, 23) + e('wait 0')
    suf += base.suffix[4:]
    control = P.drm.build_main(pre + sur + suf)
    code = P.drm.build_main(pre + var + suf)
    P.cov.gate(pre + sur + suf)
    memory = [0x5a5a0000+i for i in range(512)]
    memory[:32] = [apply(NAMED[op], table[i], table[64+i], table[128+i]) if active[i] else table[i]
                   for i in range(32)]
    expected_tab = table.copy()
    expected_tab[192:224] = [0xfeed0001]*32
    expected_tab[224:256] = [0xcafe0001 if hit else table[224+i] for i, hit in enumerate(active)]
    expected_tab[256:768] = memory
    expected_tab[768:800] = [0xcafe0002]*32
    expected_out = ([0xcdcdcdcd]*8 + [table[i] if hit else 0xdeadbeef for i, hit in enumerate(active)]
                    + [0xcdcdcdcd]*8 + [0xa5a50000+i for i in range(16)])
    expected = (expected_out, expected_tab)
    assert P.cov.simulate(control, 32, 32, 64, 2048, table) == expected
    return dict(code=code, control=control, table=table, expected=expected, n=32, wg=32, regs=64, shared=2048,
                data_dir=DATA, gate={'surrogate_full_buffer_oracle': True, 'surrogate_instruction': sur.hex(),
                    'variant_instruction': var.hex(), 'allowed_change_mask': hex(allowed),
                    'variant_decode': info, 'full_shared_fill_bytes': 2048, 'post_variant_barriers': 0,
                    'limitation': 'unknown instruction semantics not validated by surrogate'})


def summary(r, p):
    v = r.get('variant', {})
    t = v.get('table_after', [])
    return dict(name=r['name'], ok=v.get('ok'), baseline=F.matches(v, p['expected']) if v else False,
                before=sorted(set(t[192:224])), after=sorted(set(t[224:256])), after_pop=sorted(set(t[768:800])),
                returns=sorted(set(v.get('out', [])[8:40]))[:8], recovery=r.get('recovery_control_passed'),
                halted=r.get('halted'), budget=r['after']['budget_used'])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('case', choices=OPS+MASKS+BITS+EXTRA+SKIPS)
    ap.add_argument('--hardware', action='store_true')
    args = ap.parse_args()
    p = case(args.case)
    print(json.dumps({'case': args.case, 'gate': p['gate']}), flush=True)
    if args.hardware:
        r = F.hardware(args.case, p)
        print(json.dumps(summary(r,p)), flush=True)
        if r.get('halted'):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
