#!/usr/bin/env python3
"""64-bit integer forms Mesa keeps native on AGX (iadd/isub/imad with 64-bit dest), direct DRM.

Mesa lowers all int64 arithmetic except iadd64 and imul_2x32_64 (agx_compile.h
lower_int64_options); 32-bit sources are sign-extended unless `abs` is set
(Mesa umul_2x32_64 = imad with abs sources; applegpu prints the non-abs form as .sx).
iadd's shift immediate applies to the last source (nir imadshl_agx: a*b + (c << s), s <= 4).
Only assembler-round-tripped, Mesa-emitted forms are used.

Each lane loads r6, r7, r8, r9 from table regions 0..3 (64 words each), computes
r2_r3, stores r2 as its output and r3 to table region 4.
"""
import argparse, datetime, json, random, struct, subprocess, sys
from pathlib import Path
import agx_loop
import run_drm_compute as drm
import run_drm_atomic as DA

REPO = Path(__file__).resolve().parents[1]
N = 64
M32, M64 = (1 << 32)-1, (1 << 64)-1
sx = lambda v: v - (1 << 32) if v >> 31 else v
p64 = lambda lo, hi: lo | hi << 32

CASES = {   # asm, model(r6, r7, r8, r9) -> 64-bit result
    'iadd64': ('iadd r2_r3, r6_r7, r8_r9', lambda a, b, c, d: (p64(a, b)+p64(c, d)) & M64),
    'isub64': ('isub r2_r3, r6_r7, r8_r9', lambda a, b, c, d: (p64(a, b)-p64(c, d)) & M64),
    'iadd_zx32': ('iadd r2_r3, r6, r8', lambda a, b, c, d: (a+c) & M64),
    'iadd_sx32': ('iadd r2_r3, r6.sx, r8.sx', lambda a, b, c, d: (sx(a)+sx(c)) & M64),
    'iadd64_sx32': ('iadd r2_r3, r6_r7, r8.sx', lambda a, b, c, d: (p64(a, b)+sx(c)) & M64),
    'iadd64_zx32': ('iadd r2_r3, r6_r7, r8', lambda a, b, c, d: (p64(a, b)+c) & M64),
    'iadd64_zx32_lsl2': ('iadd r2_r3, r6_r7, r8, lsl 2', lambda a, b, c, d: (p64(a, b)+(c << 2)) & M64),
    'iadd64_sx32_lsl4': ('iadd r2_r3, r6_r7, r8.sx, lsl 4', lambda a, b, c, d: (p64(a, b)+(sx(c) << 4)) & M64),
    'imad_u': ('imadd r2_r3, r6, r7, r8_r9', lambda a, b, c, d: (a*b+p64(c, d)) & M64),
    'imad_s': ('imadd r2_r3, r6.sx, r7.sx, r8_r9', lambda a, b, c, d: (sx(a)*sx(b)+p64(c, d)) & M64),
    'imul_u': ('imadd r2_r3, r6, r7, 0', lambda a, b, c, d: (a*b) & M64),
    'imul_s': ('imadd r2_r3, r6.sx, r7.sx, 0', lambda a, b, c, d: (sx(a)*sx(b)) & M64),
}


def body(asm):
    e = agx_loop.encode; mov = agx_loop.chains.mov_imm
    ins = []
    for k, r in enumerate((6, 7, 8, 9)):
        ins += [e(f'iadd r4, r1, {64*k}'), e(f'device_load 0, i32, x, r{r}, u8_u9, r4, unsigned')]
    ins += [e('wait 0'), mov(2, 0xdeadbeef), mov(3, 0xdeadbeef), e(asm),
            mov(10, 256), e('iadd r4, r1, r10'), agx_loop.store(3, 8, 4), e('wait 0')]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def vectors(seed):
    r = random.Random(seed)
    E = [0, 1, 2, 3, 0x7fffffff, 0x80000000, 0x80000001, M32, 0xfffffffe, 0x55555555, 0xaaaaaaaa, 0x0000ffff, 0xffff0000, 0x10000]
    out = [(a, b, c, d) for a in E for c in E for (b, d) in [(E[(E.index(a)+3) % len(E)], E[(E.index(c)*5+1) % len(E)])]]
    out += [tuple(r.getrandbits(32) for _ in range(4)) for _ in range(250)]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/int64')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    vecs = vectors(5)
    state = {'cases': {}, 'complete': False}
    save = lambda: (out/'record.json').write_text(json.dumps(state)+'\n')
    try:
        for name, (asm, model) in CASES.items():
            code = drm.build_main(body(asm)); raw = []
            for k in range(0, len(vecs), N):
                chunk = vecs[k:k+N]; chunk += [(0, 0, 0, 0)]*(N-len(chunk))
                words = [t[j] for j in range(4) for t in chunk]+[0xcdcdcdcd]*64
                (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(words)}I', *words))
                try:
                    res = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(N), str(out/'rb'), '1', '32', str(out/'t.bin')],
                                         capture_output=True, timeout=20, env={'AGX_TABLE_OUT': str(out/'t.out'), 'PATH': '/usr/bin'})
                except subprocess.TimeoutExpired:
                    state['fault'] = name; raise RuntimeError('timeout on '+name)
                smp = [json.loads(l) for l in res.stdout.decode().splitlines() if '"rep"' in l]
                if res.returncode or not smp or not all(s['fw_ts'][0] and s['fw_ts'][1] and s['host_ns'] < 50_000_000 for s in smp):
                    state['fault'] = name; raise RuntimeError('fault on '+name)
                lo = list(struct.unpack(f'<{N+32}I', (out/'rb').read_bytes()))[8:8+N]
                hi = list(struct.unpack(f'<{len(words)}I', (out/'t.out').read_bytes()))[256:256+N]
                raw += [[*chunk[i], lo[i], hi[i]] for i in range(N) if k+i < len(vecs)]
            bad = [r for r in raw if p64(r[4], r[5]) != model(*r[:4])]
            state['cases'][name] = {'asm': asm, 'vectors': len(raw), 'mismatches': len(bad),
                                    'examples': [[hex(x) for x in r]+[hex(model(*r[:4]))] for r in bad[:6]], 'raw': raw}
            save()
            print(json.dumps({'case': name, 'vectors': len(raw), 'mismatches': len(bad), 'ex': state['cases'][name]['examples'][:2]}), flush=True)
        state['complete'] = True
    except Exception as e:
        state['error'] = str(e)
    finally:
        save(); print(json.dumps({'complete': state['complete'], 'output': str(out), 'error': state.get('error')}))


if __name__ == '__main__':
    main()
