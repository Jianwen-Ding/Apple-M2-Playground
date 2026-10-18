#!/usr/bin/env python3
"""Preshader (preamble) follow-ups (safe-09). Direct DRM, straight-line, no loops; preambles use only uniform_store, mov_imm, get_sr, ALU
and the device atomic add (no return) that earlier runs executed, always ending in `stop`; no barriers.

  uniforms   which uniforms a preamble can write and the main shader can read, versus the CDM launch word's `Uniform register count`
             field (groups of 64 halves): the preamble writes u<U> = 0xC0DE0000 | U for every U inside the allocation except the
             harness's u4..u9; the main shader reads u0..u255 into the table. Reads beyond the allocation show what is there.
  count      the preamble adds 1 to a per-core counter (device atomic, no return): runs per core per dispatch, with several commands in
             one submit (AGX_CMDS) and several submits.
  regs       a preamble that touches registers up to r63 / r127 (declared main registers 16): does occupancy change (occupancy2 counter)?
  cost       firmware time of a dispatch with no preamble, a 1-instruction preamble and preambles of 64 / 256 ALU instructions.
  run_drm_preshader.py offline|uniforms|count|regs|cost
"""
import argparse, json, os, struct, subprocess, sys, time
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA, gpu_safety
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_opcode_describe import get_sr

REPO = Path(__file__).resolve().parents[1]
mov, enc = chains.mov_imm, agx_loop.encode
STOP = bytes.fromhex('8800')
SENT = 0xcdcdcdcd
HARNESS = range(4, 10)           # u4..u9 hold index offset, count, output VA, table VA
LANES = 32


def write_uniform(u, value):
    """mov_imm r1 <- value; uniform_store into u<u> (halves 2u, 2u+1): immediate offset up to half 254, else a register offset."""
    b = mov(1, value)
    if 2*u <= 254:
        return b+agx_loop.uniform_store(1, 2*u)
    return b+mov(2, 2*u)+enc('uniform_store 2, i16, xy, 0, r1l_r1h, r2')


def preamble_uniforms(limit, sample=False):
    """sample: write only every 4th uniform below u160 plus all above (the preamble must fit between its USC offset and the code)."""
    pre = b''
    for u in range(limit):
        if u in HARNESS or (sample and u < 160 and u % 4):
            continue
        pre += write_uniform(u, 0xC0DE0000 | u)
    return pre+STOP


def main_read_all(n_uniforms=256, S=LANES):
    body = b''
    for u in range(n_uniforms):
        body += mov(15, u*S)+enc('iadd r5, r1, r15')+enc(f'iadd r8, u{u}, 0')+agx_loop.store(8, 8, 5)
        if u % 8 == 7:
            body += enc('wait 0')
    return body+enc('wait 0')+bytes.fromhex('620978563412')


def run(exe, out, code, pre, n, table_words, env, repeats=1, gprs='64', init=SENT):
    (out/'c.bin').write_bytes(code+bytes(16))
    (out/'t.bin').write_bytes(struct.pack('<I', init)*table_words)
    e = {'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out'), **env}
    if pre is not None:
        (out/'pre.bin').write_bytes(pre)
        e.update({'AGX_PRESHADER': '1', 'AGX_PRESHADER_CODE': str(out/'pre.bin')})
    gpu_safety.require_budget(1)
    r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), str(repeats), gprs, str(out/'t.bin')],
                       capture_output=True, timeout=60, env=e)
    ev = [json.loads(l) for l in r.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
    smp = [x for x in ev if 'rep' in x]
    if b'"failure":"' in r.stdout and not smp:      # a harness precondition refused the run before any submission: not a GPU event
        sys.exit('harness refused the run: '+r.stdout.decode(errors='replace')[-120:])
    if r.returncode or len(smp) != repeats or not all(x['fw_ts'][0] and x['fw_ts'][1] and x['host_ns'] < 50_000_000 for x in smp):
        gpu_safety.record('preshader run failed')
        sys.exit('run failed / hang signature: '+r.stdout.decode(errors='replace')[-300:])
    t = struct.unpack(f'<{table_words}I', (out/'t.out').read_bytes())
    return t, [x['fw_ts'][1]-x['fw_ts'][0] for x in smp]


def cmd_uniforms(a, exe, out):
    rec = {'configs': []}
    for field in a.fields:
        limit = 32*field                     # uniforms inside the allocation: 64 halves per group
        pre = preamble_uniforms(limit, sample=field >= 7)
        code = drm.build_main(main_read_all())
        t, fw = run(exe, out, code, pre, LANES, 256*LANES, {'AGX_UNIFORM_GROUPS': str(field)})
        vals = [t[u*LANES] for u in range(256)]
        lane_same = all(len({t[u*LANES+l] for l in range(LANES)}) == 1 for u in range(256))
        res = {'field': field, 'allocated_uniforms': limit, 'values': vals, 'lanes_agree': lane_same, 'fw_ns': fw[0], 'preamble_bytes': len(pre)}
        rec['configs'].append(res)
        expect = [u for u in range(limit) if u not in HARNESS and not (field >= 7 and u < 160 and u % 4)]
        written = sum(1 for u in expect if vals[u] == 0xC0DE0000 | u)
        res['written_expected'] = len(expect); res['written_read_back'] = written
        beyond = [(u, hex(vals[u])) for u in range(limit, 256) if vals[u] not in (0, SENT)][:6]
        print(f'field {field}: {limit} uniforms allocated, {written} of {len(expect)} written ones read back; beyond: nonzero {len([u for u in range(limit,256) if vals[u]])} of {256-limit}; sample {beyond}', flush=True)
    return rec


CNT_BASE = 0      # table words 0..63: per-core preamble run counters


def preamble_count():
    """Per-core run counter: table[SR20] += 1 with a device atomic add (no return), addressed through u8_u9."""
    return get_sr(20, 1)+mov(2, 1)+agx_loop.atomic_add(8, 1, 2)+enc('wait 0')+STOP


def cmd_regs(a, exe, out):
    """Does a preamble change SR19 (register allocation) or the occupancy of the main shader? The preambles only touch registers inside the
    declared count (a preamble using more than the declared registers could overrun its allocation: not run)."""
    import run_drm_occupancy2 as O
    rec = {'configs': []}
    wide = b''.join(mov(r, 0) for r in range(2, 31))+STOP                  # r2..r30 (declared 64 halves = r0..r31)
    variants = {'none': None, 'stop': STOP, 'regs_r2_r30': wide}
    sr19 = drm.build_main(get_sr(19, 6)+enc('iadd r7, r1, 0')+agx_loop.store(6, 8, 7)+enc('wait 0')+bytes.fromhex('620978563412'))
    for name, pre in variants.items():
        t, fw = run(exe, out, sr19, pre, 64, 64, {'AGX_LOCAL_X': '64'}, gprs='64')
        sr19_vals = sorted(set(t[:64]))
        occ = {}
        for g in (16, 64):
            code = drm.build_main(O.body(16000))
            t2, fw2 = run(exe, out, code, pre, 1 << 18, 640, {'AGX_LOCAL_X': '128'}, gprs=str(g), init=0)
            occ[g] = max(t2[O.MAX:O.MAX+64])/32
        res = {'preamble': name, 'sr19_values': sr19_vals, 'peak_groups_by_gprs': occ}
        rec['configs'].append(res)
        print(name, res, flush=True)
    return rec


def cmd_cost(a, exe, out):
    """Firmware time of a dispatch of 2,048 workgroups (65,536 lanes) with no preamble, a 1-instruction preamble, and preambles of 64 / 256
    dependent ALU instructions; 15 interleaved samples with the clock keeper running."""
    import statistics as st
    alu = lambda n: mov(1, 1)+b''.join(enc('iadd r1, r1, 1') for _ in range(n))+STOP
    variants = {'none': None, 'stop': STOP, 'alu64': alu(64), 'alu256': alu(256)}
    code = drm.build_main(bytes.fromhex('620978563412'))
    stop_file = out/'keeper-stop'; stop_file.unlink(missing_ok=True)
    keeper = subprocess.Popen([sys.executable, '-B', 'scripts/clock_keeper.py', '--seconds', '600', '--stop-file', str(stop_file)], cwd=REPO,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    samples = {k: [] for k in variants}
    try:
        for i in range(15):
            for name, pre in variants.items():
                t, fw = run(exe, out, code, pre, 65536, 64, {}, init=0)
                samples[name].append(fw[0])
    finally:
        stop_file.touch()
        try:
            keeper.wait(timeout=60)
        except subprocess.TimeoutExpired:
            keeper.kill()
    rec = {'samples_ns': samples, 'keeper_stopped': keeper.poll() is not None}
    base = st.median(samples['none'])
    for k, v in samples.items():
        print(f'{k:7s} median {st.median(v):8.0f} ns  min {min(v)} max {max(v)}  (median minus none: {st.median(v)-base:+.0f} ns)', flush=True)
    return rec


def cmd_count(a, exe, out):
    rec = {'configs': []}
    body = bytes.fromhex('620978563412')                       # the control main's own epilogue is enough: every lane just ends
    code = drm.build_main(body)
    for cmds, repeats in ((1, 1), (1, 3), (2, 1), (2, 3), (4, 1), (4, 2)):
        (out/'t.bin').write_bytes(bytes(4*64))
        t, fw = run(exe, out, code, preamble_count(), 65536, 64, {'AGX_CMDS': str(cmds)}, repeats=repeats)
        counts = [(x - SENT) & 0xffffffff for x in t]       # run() initialises the table to SENT
        used = [c for c in counts if 0 < c < 100000]
        res = {'commands_per_submit': cmds, 'submits': repeats, 'dispatches': cmds*repeats, 'cores_with_runs': len(used), 'per_core': sorted(set(used)),
               'total_runs': sum(used), 'fw_ns': fw}
        rec['configs'].append(res)
        print(f"{cmds} command(s) x {repeats} submit(s) = {cmds*repeats} dispatches: cores with a preamble run {len(used)}, per-core counts {sorted(set(used))}, total {sum(used)}", flush=True)
    return rec


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'uniforms', 'count', 'regs', 'cost'])
    p.add_argument('--fields', type=lambda s: [int(x) for x in s.split(',')], default=[1, 2, 3, 4, 5])
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/preshader'))
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        # gate: the program and preamble run in agx_run (the simulator's uniform file is 256 uniforms)
        for field in (1, 5):
            pre = preamble_uniforms(32*field)
            code = drm.build_main(main_read_all())
            (out/'c.bin').write_bytes(code+bytes(16)); (out/'pre.bin').write_bytes(pre)
            R = REPO.parent/'AGX-Performance-Simulator/rust/target/release/agx_run'
            tb = out/'tb.bin'; tb.write_bytes(struct.pack('<I', SENT)*(256*LANES+LANES))
            outb = out/'ob.bin'; outb.write_bytes(struct.pack('<%dI' % (8+LANES+8+16), *([SENT]*(8+LANES+8+16))))
            dump = out/'dump.bin'
            va_o, va_t = 0x1100008000, 0x1100100000
            r = subprocess.run([str(R), str(out/'c.bin'), '--grid', '32,1,1', '--wg', '32,1,1', '--regs', '64', '--preamble', str(out/'pre.bin'),
                                '--uniform', f'5={LANES}', '--uniform', f'6={va_o & 0xffffffff}', '--uniform', f'7={va_o >> 32}',
                                '--uniform', f'8={va_t & 0xffffffff}', '--uniform', f'9={va_t >> 32}', '--map', f'{va_o:#x}={outb}', '--map', f'{va_t:#x}={tb}',
                                '--dump', f'{va_t:#x}={4*256*LANES}:{dump}', '--alloc-regs', '64', '--vm-slot', '0', '--pipeline', '4096'],
                               capture_output=True, text=True)
            if r.returncode:
                sys.exit('simulator refused: '+(r.stdout+r.stderr)[-300:])
            t = struct.unpack(f'<{256*LANES}I', dump.read_bytes())
            good = sum(1 for u in range(32*field) if u not in HARNESS and t[u*LANES] == 0xC0DE0000 | u)
            print(f'simulator, field {field}: {good} of {32*field-len(HARNESS)} written uniforms read back')
        return
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'uniforms': cmd_uniforms, 'count': cmd_count, 'regs': cmd_regs, 'cost': cmd_cost}.get(a.mode, lambda *x: sys.exit('mode not implemented yet'))(a, exe, out)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
