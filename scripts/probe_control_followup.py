#!/usr/bin/env python3
"""Bounded unsafe probes; simulator-gated surrounding code, recorded faults and recovery controls.

Default: offline. --hardware submits one selected variant. A fault is recorded,
then a known-good control checks recovery; failed recovery ends the session.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import probe_ret_landing as P

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'results/2026-10-17-call-ret/followup'
SCRATCH = Path('/scratch/apple-m2-playground/control-followup')


def roundtrip(indirect=False, nested=False):
    e, mov, st = P.RS.e, P.RS.mov, P.RS.agx_loop.store
    site = P.drm.control_main()[1]
    pre = e('iadd r20, r1, 0') + mov(21, 32) + e('iadd r21, r20, r21')
    pre += mov(22, 64) + e('iadd r22, r20, r22')
    pre += mov(23, 0xfeed0001) + st(23, 8, 20) + e('wait 0')
    if indirect:
        pre += mov(30, 0)
    call_pc = site + len(pre)
    continuation = e('pop_exec r0l, 2') + mov(23, 0xcafe0002) + st(23, 8, 21)
    continuation += st(1, 8, 22) + e('wait 0') + e('stop')
    func_pc = call_pc + 6 + len(continuation)
    if indirect:
        pre = pre[:-6] + mov(30, 0x2000 + func_pc)
    function = mov(23, 0xf00d0001) + st(23, 8, 20) + e('wait 0')
    inner_call_pc = None
    if nested:
        function += e('iadd r29, r1, 0')
        inner_call_pc = func_pc + len(function)
        function += bytes(6) + e('pop_exec r0l, 2') + e('iadd r1, r29, 0')
    ret_pc = func_pc + len(function)
    function += e('ret r1') + e('wait 0') * 2
    inner_ret_pc = None
    if nested:
        inner_pc = func_pc + len(function)
        function += mov(24, 96) + e('iadd r24, r20, r24') + mov(23, 0xb00d0001)
        function += st(23, 8, 24) + e('wait 0')
        inner_ret_pc = func_pc + len(function)
        function += e('ret r1') + e('wait 0') * 2
        at = inner_call_pc - func_pc
        function = function[:at] + (0xc010 | ((inner_pc-inner_call_pc)<<16)).to_bytes(6,'little') + function[at+6:]
    code = P.drm.build_main(pre + (0xc010 | ((func_pc - call_pc) << 16)).to_bytes(6, 'little') + continuation + function)
    off = call_pc + 6 - ret_pc
    jump = e(f'jmp_exec_any pc{off:+}', f'jmp_exec_any pc{off:+}')
    control = code[:ret_pc] + jump + code[ret_pc+6:]
    if nested:
        off2 = inner_call_pc + 6 - inner_ret_pc
        j2 = e(f'jmp_exec_any pc{off2:+}', f'jmp_exec_any pc{off2:+}')
        control = control[:inner_ret_pc] + j2 + control[inner_ret_pc+6:]
    if indirect:
        code = code[:call_pc] + e('call r30') + e('wait 0') * 2 + code[call_pc+6:]
    want_out = [0xcdcdcdcd] * 48 + [0xa5a50000+i for i in range(16)]
    want_tab = [0xf00d0001]*32 + [0xcafe0002]*32 + [0x2000+call_pc+6]*32 + [0xb00d0001 if nested else 0]*32
    assert P.simulate(control) == (want_out, want_tab)
    P.cov.gate(code, allow=('call', 'ret'))
    try:
        P.simulate(code)
    except RuntimeError as exc:
        assert ('register form' if indirect else 'ret semantics unresolved') in str(exc)
    else:
        raise AssertionError('ret unexpectedly accepted')
    return dict(code=code, control=control, table=P.TABLE, n=32, wg=32, regs=64,
                expected=(want_out, want_tab), gate={'direct_call_and_return_jump_surrogate': True,
                'variant_rejected_as_unresolved': True, 'call_pc': call_pc, 'ret_pc': ret_pc,
                'return_pc': call_pc+6})


def case(name):
    P.cov.install()
    P.RET_PC, P.VALUE, P.LANDINGS = 512, 1024, (1024, 1536, 2048, 2560)
    if name.startswith('atomic-gap'):
        import probe_atomics as A
        spec = name.removeprefix('atomic-gap').split('-op')
        op = int(spec[1]) if len(spec) == 2 else 0
        bits = tuple(int(b) for b in spec[0].split('+'))
        assert all(b in (26, 28, 29, 31, 42, 43, 44) for b in bits) and len(bits) in (1, 2)
        assert op in (0, 2, 3) and (op == 0 or bits == (29,))
        bit = bits[0]
        table = A.table_b('atomic-gap-controls')
        if op == 3:
            for i in range(0, 32, 3):
                table[A.S_WORD + 2*i + 1] = table[i]
        pre, suf = A.common(1)
        sur = A.atomic_bytes(op, 1)
        flip = 0
        for b in bits:
            flip |= 1 << b
        var = (int.from_bytes(sur, 'little') ^ flip).to_bytes(8, 'little')
        assert (int.from_bytes(var, 'little') ^ int.from_bytes(sur, 'little')) == flip
        control, code = (P.drm.build_main(pre + op + suf) for op in (sur, var))
        tab = table.copy()
        for i in range(32):
            src = table[A.S_WORD + 2*i]
            if op == 0:
                tab[i] = (table[i] + src) & 0xffffffff
            elif op == 2 or table[i] == table[A.S_WORD + 2*i + 1]:
                tab[i] = src
        out = [0xcdcdcdcd]*8 + table[:32] + [0xcdcdcdcd]*8 + [0xa5a50000+i for i in range(16)]
        P.cov.gate(pre + sur + suf)
        assert P.cov.simulate(control, 32, 32, 64, 0, table) == (out, tab)
        return dict(code=code, control=control, table=table, n=32, wg=32, regs=64,
                    expected=(out, tab), data_dir=(ROOT/'results/2026-10-19-atomic-pairs' if len(bits) == 2
                                                         else ROOT/'results/2026-10-17-atomic-gap-bits'),
                    gate={('baseline_add_matches_independent_oracle' if op == 0 else 'baseline_matches_independent_oracle'): True, 'changed_bits': bits,
                          'baseline_instruction': sur.hex(), 'variant_instruction': var.hex(),
                          'variant_decode': P.cov.ASMB.info(var), 'limitation': 'unmeasured control bit; surrogate gate only'})
    if name in ('call-ret-pop2', 'callreg-ret-pop2', 'call-nested-pop2'):
        return roundtrip(indirect=name.startswith('callreg'), nested=name == 'call-nested-pop2')
    maps = ('ret-byte-buffer', 'ret-shift-pc', 'ret-shift-value', 'ret-byte-nopop', 'ret-byte-pop2')
    if name in ('ret-pop0', 'ret-pop1', 'ret-pop3', 'ret-r1-pop1') + maps:
        if name in maps:
            P.RET_PC = 768 if name == 'ret-shift-pc' else 512
            P.VALUE = 0x2500 if name == 'ret-shift-value' else 0x2400
            v, pc = P.VALUE, P.RET_PC
            P.LANDINGS = tuple(sorted({v - 0x2000, pc + v - 0x2000, 1536, v, pc + v,
                                       2*v - 0x2000, pc + 2*v - 0x2000, 2*v, pc + 2*v}))
        reenable = None if name == 'ret-byte-nopop' else (1 if name in maps else int(name[-1]))
        if name == 'ret-byte-pop2':
            reenable = 2
        code, control = P.build(reenable=reenable)
        if name == 'ret-r1-pop1':
            code = code[:P.RET_PC] + P.RS.e('ret r1') + code[P.RET_PC + 2:]
        gate = P.gate(code, control)
        return dict(code=code, control=control, table=P.TABLE, n=32, wg=32, regs=64,
                    expected=P.expected(1), gate=gate, ret_pc=P.RET_PC, target=P.VALUE)
    raise ValueError(name)


def run_bounded(argv, env, timeout=10, kill_timeout=2):
    """Bound both dispatch wait and post-SIGKILL pipe drain (a task may be stuck in the driver)."""
    proc = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    r = {'command': argv, 'environment': env, 'pid': proc.pid}
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as ex:
        r['host_timeout'] = True
        # Read only this probe's metadata; retain mappings before killing it.
        r['process_at_timeout'] = {}
        for name in ('status', 'wchan', 'maps'):
            try:
                r['process_at_timeout'][name] = Path(f'/proc/{proc.pid}/{name}').read_text()
            except OSError as error:
                r['process_at_timeout'][name] = str(error)
        proc.kill()
        try:
            out, err = proc.communicate(timeout=kill_timeout)
        except subprocess.TimeoutExpired as drain:
            r['host_process_stuck'] = True
            out, err = drain.stdout or ex.stdout or b'', drain.stderr or ex.stderr or b''
            # Do not wait indefinitely for an uninterruptible kernel task.
            proc.stdout.close()
            proc.stderr.close()
    r.update(returncode=proc.poll(), stdout=out.decode(errors='replace'), stderr=err.decode(errors='replace'))
    return r


def run_one(runner, code, p, label):
    """Retain full stdout/stderr, timestamps and even partial failed readbacks."""
    d = runner.out / label
    d.mkdir()
    (d / 'code.bin').write_bytes(code + bytes(16))
    (d / 'table.bin').write_bytes(struct.pack(f"<{len(p['table'])}I", *p['table']))
    argv = [str(runner.exe), '/dev/dri/renderD128', str(d / 'code.bin'), str(p['n']), str(d / 'out.bin'), '1',
            str(p['regs']), str(d / 'table.bin')]
    env = {'PATH': '/usr/bin', 'AGX_LOCAL_X': str(p['wg']), 'AGX_TABLE_OUT': str(d / 'table-out.bin')}
    if p.get('shared', 0):
        from run_drm_tg_layout import shared_word
        env['AGX_SHARED_WORD'] = str(shared_word(p['shared']))
    before = len(P.gpu_safety.used())
    r = run_bounded(argv, env)
    lines = []
    for line in r['stdout'].splitlines():
        if line.startswith('{'):
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                r.setdefault('incomplete_json_lines', []).append(line)
    smp = [s for s in lines if 'rep' in s]
    r['ok'] = (not r.get('host_timeout') and not r.get('incomplete_json_lines')
               and r['returncode'] == 0 and len(smp) == 1 and len(smp[0].get('fw_ts', [])) == 2
               and all(smp[0]['fw_ts']))
    r['samples'] = smp
    for file, key in (('out.bin', 'out'), ('table-out.bin', 'table_after')):
        f = d / file
        if f.exists():
            b = f.read_bytes()
            whole = len(b) // 4 * 4
            r[key] = list(struct.unpack(f'<{whole//4}I', b[:whole]))
            if whole != len(b):
                r[key + '_partial_tail_hex'] = b[whole:].hex()
                r['ok'] = False
    if r['ok']:
        r['fw_ns'] = smp[0]['fw_ts'][1] - smp[0]['fw_ts'][0]
    elif smp or r.get('host_timeout'):
        if len(P.gpu_safety.used()) == before:
            P.gpu_safety.record(f'control-followup {runner.out.name}/{label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(name, p):
    directory = p.get('data_dir', DATA)
    path = directory / f'{name}.json.gz'
    if path.exists():
        raise SystemExit(f'refusing to overwrite {path}')
    P.gpu_safety.require_budget(1)
    directory.mkdir(parents=True, exist_ok=True)
    runner = P.bench.Runner(SCRATCH / name)
    rec = dict(name=name, utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), before=P.snapshot(),
               code=p['code'].hex(), control_code=p['control'].hex(), table_in=p['table'], n=p['n'], wg=p['wg'],
               regs=p['regs'], gate=p['gate'], script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               simulator_sha256=hashlib.sha256(P.cov.RUN.read_bytes()).hexdigest(),
               harness_sha256=hashlib.sha256((P.bench.REPO / 'tests/drm_compute.c').read_bytes()).hexdigest())
    if p.get('shared', 0):
        rec['shared'] = p['shared']
    start = Path('/save/kernel.log').stat().st_size

    def save():
        rec['after'] = P.snapshot()
        rec['kernel_log_delta'] = Path('/save/kernel.log').read_bytes()[start:].decode(errors='replace')
        with gzip.GzipFile(filename=str(path), mode='wb', mtime=0) as f:
            f.write((json.dumps(rec, sort_keys=True) + '\n').encode())

    rec['phase'] = 'pre-control'
    save()  # Exact program and inputs survive even if the first submission wedges.
    rec['control_before'] = run_one(runner, p['control'], p, 'control-before')
    if not matches(rec['control_before'], p['expected']):
        rec['halted'] = 'pre-control failed; no variant submitted'
        save()
        return rec
    rec['phase'] = 'variant'
    save()
    rec['variant'] = run_one(runner, p['code'], p, 'variant')
    save()
    if rec['variant'].get('host_process_stuck'):
        rec['halted'] = 'probe process still blocked after SIGKILL; no more submissions'
        save()
        return rec
    if not rec['variant']['ok']:
        time.sleep(2)
    rec['phase'] = 'recovery-control'
    save()
    rec['control_after'] = run_one(runner, p['control'], p, 'control-after')
    rec['recovery_control_passed'] = matches(rec['control_after'], p['expected'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed; GPU recovery not established, no more submissions'
    rec['phase'] = 'finished'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('case')
    ap.add_argument('--hardware', action='store_true')
    a = ap.parse_args()
    p = case(a.case)
    print(json.dumps({'case': a.case, 'gate': p['gate']}), flush=True)
    if a.hardware:
        r = hardware(a.case, p)
        v = r.get('variant', {})
        print(json.dumps({'case': a.case, 'variant_ok': v.get('ok'), 'fw_ns': v.get('fw_ns'),
                          'markers': sorted(set(v.get('table_after', [])[32:64])),
                          'recovery_control_passed': r.get('recovery_control_passed'),
                          'halted': r.get('halted'), 'budget_used': r['after']['budget_used']}), flush=True)
        if r.get('halted'):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
