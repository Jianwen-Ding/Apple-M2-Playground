#!/usr/bin/env python3
"""Does another SIMD group observe shared memory written before a threadgroup ending opcode? (owner-approved unsafe)

One 64-lane workgroup (two SIMD groups, one core). Group 0 issues a threadgroup atomic add (+1 to
shared word 0) and then either a second atomic sub (-1, CONTROL, both Mesa op 0/1 no-fault forms) or
the ending opcode 11 (TEST: exact bytes of the recorded tg-op11 case). Group 1 delays, then reads
shared word 0 eight times. Outcome counts per lane: saw32 (any read == 32), end0 (last read == 0).
If op 11 wrote and published like the plain sub, TEST matches CONTROL (late reads 0); if op 11 did
not write (or not visibly), TEST stays at 32. A second 0x68 barrier in CONTROL makes it exactly
predictable; TEST cannot have one (group 0 ends first), so TEST is outcome counts only.

New beyond the recorded tg-op11 case: a second group runs while group 0 ends. Mask discipline is
the measured partial-mask form (group 0 fully active / group 1 empty at the ending op: ends group 0,
group 1 skips and continues). Straight-line, no loops, no spin-waits, no new encodings. Every
program is decode-gated; CONTROL is exactly gated in agx_run; TEST is gated via its op1 surrogate.
Hardware goes through probe_control_followup.hardware (watchdog, recovery control, memory
diagnostics). Stop at the first fault.
  probe_tg_end_visible.py [--lanes N] [--repeats R] [--full]   # default: small-first (128 lanes, 1 rep)
"""
import argparse, json
from pathlib import Path
import probe_control_followup as F

P = F.P
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'results/2026-10-19-tg-end-visible'
SENT = 0xcdcdcdcd
ALIVE = 0xcafe0001
REGS = 64
SHARED = 2048


def build(op11, barrier, n, remark=False):
    P.cov.install()
    import probe_atomics as A
    import run_drm_atomic as DA
    from run_drm_opcode_describe import get_sr, WAIT
    from run_drm_tg_layout import tg
    e, mov, st = P.RS.e, P.RS.mov, P.RS.agx_loop.store
    # shared word 0 = 0 (all lanes store 0 concurrently: benign), then align both groups
    ins = [mov(23, 0), tg(False, 'i32', 23), WAIT, bytes.fromhex('6800')]
    # group mask: SR53 == 0 (group 0) active
    ins += [get_sr(53, 4), mov(27, 0), e('if_icmp r0l, ueq, r4, r27, 1')]
    # atomic operands: r22 = shared byte 0, r6 = 1, r5 = return (discarded)
    ins += [mov(22, 0), mov(6, 1), mov(5, 0)]
    add = A.mesa_local_atomic(0, 10, 44, 12, True)
    sub = A.mesa_local_atomic(1, 10, 44, 12, True)
    if op11:
        allowed = 0xf << 24
        var = (sub & ~allowed) | (11 << 24)
        ins += [add.to_bytes(10, 'little'), var.to_bytes(10, 'little')]
        second = var
    else:
        ins += [add.to_bytes(10, 'little'), sub.to_bytes(10, 'little')]
        second = sub
    # alive marker (group 0 only; ended lanes in TEST skip it)
    ins += [mov(23, ALIVE), mov(20, 2*n), e('iadd r29, r1, r20'), st(23, 8, 29)]
    if barrier:
        ins += [WAIT, bytes.fromhex('6800')]
    # reconverge, delay, 8 reads with counts
    ins += [e('pop_exec r0l, 1')]
    ins += [mov(7, 0)] + [e('iadd r7, r7, 1') for _ in range(32)]
    ins += [mov(10, 0), mov(27, 32)]
    for _ in range(8):
        ins += [tg(True, 'i32', 9), e('wait 0'),
                e('icmpsel ueq, r11, r9, r27, 1, 0'), e('iadd r10, r10, r11')]
    ins += [mov(20, 0), e('iadd r29, r1, r20'), st(10, 8, 29)]           # saw32 count -> region 0
    ins += [e('icmpsel ueq, r11, r9, 0, 1, 0'),
            mov(20, n), e('iadd r29, r1, r20'), st(11, 8, 29), e('wait 0')]  # end0 -> region 1
    if remark:
        # explicit group-1 re-assertion: does not rely on the first pop
        ins += [mov(27, 1), e('if_icmp r0l, ueq, r4, r27, 1'),
                mov(23, 0xbeef0001), mov(20, 3*n), e('iadd r29, r1, r20'), st(23, 8, 29),
                e('pop_exec r0l, 1')]
    ins += [e('iadd r2, r10, 0')]
    body = b''.join(ins)
    DA.decode_lengths(body, [len(i) for i in ins])
    return P.drm.build_main(body), second


REMARK = 0xbeef0001


def check_control(n, remark=False):
    """Exact agx_run gate for CONTROL (barrier-separated: deterministic). Returns the sim table."""
    import run_drm_atomic as DA  # noqa
    code, _ = build(False, True, n, remark)
    table = [SENT]*((4 if remark else 3)*n)
    o, t = P.cov.simulate(code, n, 64, REGS, SHARED, table)
    assert o[8:8+n] == [0]*n, 'control sim (sequential): no lane ever reads 32'
    if remark:
        mk = t[3*n:4*n]
        assert all(mk[i] == REMARK for i in range(n) if (i & 63) >= 32), 'control: group-1 remark markers'
        assert all(mk[i] == SENT for i in range(n) if (i & 63) < 32), 'control: group-0 masked at remark'
    return t


def check_surrogate(n, remark=False):
    """Termination + structural gate for the TEST layout with a safe op (sim rejects op 11)."""
    code, _ = build(False, False, n, remark)
    table = [SENT]*((4 if remark else 3)*n)
    o, t = P.cov.simulate(code, n, 64, REGS, SHARED, table)
    return t


def case(n, barrier, remark=False):
    code_c, _ = build(False, barrier, n, remark)
    code_t, var = build(True, False, n, remark)
    nw = 4 if remark else 3
    table = [SENT]*(nw*n)
    # CONTROL is barrier-separated, hence deterministic on hardware too: group-1 reads happen
    # strictly after group 0's add+sub, so every read is 0; alive markers only on group-0 lanes.
    alive = [ALIVE if (i & 63) < 32 else SENT for i in range(n)]
    exp_table = [0]*n + [1]*n + alive
    if remark:
        exp_table += [REMARK if (i & 63) >= 32 else SENT for i in range(n)]
    rounded = (n+31)//32*32
    exp_out = [0xcdcdcdcd]*8 + [0]*n + [0xcdcdcdcd]*(rounded-n+8) + [0xa5a50000+i for i in range(16)]
    return dict(code=code_t, control=code_c, table=table, expected=(exp_out, exp_table), n=n, wg=64, regs=REGS, shared=SHARED,
                data_dir=DATA, variant_op11=hex(var),
                gate={'control': 'exact agx_run + barrier-separated hardware oracle', 'test': 'op1 surrogate + decode gate'})


def analyze(t, n, label):
    saw = t[0:n]
    end = t[n:2*n]
    alive = t[2*n:3*n]
    n0 = [i for i in range(n) if (i & 63) < 32]
    n1 = [i for i in range(n) if (i & 63) >= 32]
    return {'label': label,
            'g0_alive': sum(1 for i in n0 if alive[i] == ALIVE), 'g0_n': len(n0),
            'g1_alive': sum(1 for i in n1 if alive[i] == ALIVE),
            'saw32_g1': sum(1 for i in n1 if saw[i] not in (SENT,)) and sum(saw[i] for i in n1 if isinstance(saw[i], int)),
            'end0_g1': sum(1 for i in n1 if end[i] == 1),
            'saw_vals': sorted(set(saw))[:8], 'end_vals': sorted(set(end))[:8]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'])
    ap.add_argument('--lanes', type=int, default=128)
    ap.add_argument('--repeats', type=int, default=1)
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--remark', action='store_true', help='v2: explicit group-1 re-assertion marker')
    a = ap.parse_args()
    if a.full:
        a.lanes, a.repeats = 16384, 3
    import gpu_safety
    print(json.dumps({'mode': 'full' if a.full else 'small-first', 'lanes': a.lanes,
                      'budget': gpu_safety.require_budget(1)}), flush=True)
    if a.mode == 'offline':
        t = check_control(a.lanes, a.remark)
        n0 = [i for i in range(a.lanes) if (i & 63) < 32]
        n1 = [i for i in range(a.lanes) if (i & 63) >= 32]
        saw, end, alive = t[0:a.lanes], t[a.lanes:2*a.lanes], t[2*a.lanes:3*a.lanes]
        assert all(s == 0 for s in saw), 'control: barrier-separated reads must all be 0'
        assert all(v == 1 for v in end), 'control: every last read must be 0'
        assert all(alive[i] == ALIVE for i in n0), 'control: group-0 lanes must store ALIVE'
        assert all(alive[i] == SENT for i in n1), 'control: group-1 lanes must not store ALIVE'
        print('control: exact agx_run oracle holds (saw32=0, end0=1 everywhere; ALIVE on group-0 lanes only)')
        ts = check_surrogate(a.lanes, a.remark)
        ssaw = ts[0:a.lanes]
        assert all(isinstance(v, int) and 0 <= v <= 8 for v in ssaw), 'surrogate counts in range'
        print('surrogate: terminates in agx_run, counts in range')
        return
    tag = 'tg-op11-cross-group2' if a.remark else 'tg-op11-cross-group'
    for rep in range(a.repeats):
        p = case(a.lanes, True, a.remark)
        p['data_dir'] = DATA
        name = f'{tag}-r{rep}'
        r = F.hardware(name, p)
        print(json.dumps({'rep': rep, 'halted': r.get('halted'),
                          'recovery': r.get('recovery_control_passed'),
                          'budget': r['after']['budget_used']}), flush=True)
        if r.get('halted'):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
