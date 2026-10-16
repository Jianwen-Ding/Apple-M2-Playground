"""Pre-GPU gate shared by direct-DRM runners: the exact kernel must end with `stop`, run to completion in the
simulator's agx_run (AGX-Performance-Simulator) with the harness's uniforms and output layout, and write the
expected words. A runner calls require(code, count, want) before any submission."""
import json, os, struct, subprocess, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SIM = Path(os.environ.get('AGX_SIM', REPO.parent/'AGX-Performance-Simulator'))
GUARD, TAIL = 0xcdcdcdcd, 0xa5a50000


def layout(count):
    rounded = (count+31)//32*32
    return rounded, 8+rounded+8+16


def simulate(code, count, wg=32, regs=16, max_steps=400_000_000):
    """Return (output words, agx_run stats) for one dispatch of `count` lanes (grid rounded to 32)."""
    rounded, words = layout(count)
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        init = [GUARD]*(words-16)+[TAIL+i for i in range(16)]
        (t/'o.bin').write_bytes(struct.pack(f'<{words}I', *init))
        (t/'k.bin').write_bytes(code+bytes(16))
        r = subprocess.run([str(SIM/'rust/target/release/agx_run'), str(t/'k.bin'), '--grid', str(rounded), '--wg', str(wg),
                            '--regs', str(regs), '--uniform', '4=0', '--uniform', f'5={count}', '--uniform', '6=0x100000',
                            '--uniform', '7=0x11', '--map', f'0x1100100000={t/"o.bin"}',
                            '--dump', f'0x1100100000={4*words}:{t/"r.bin"}', '--max-steps', str(max_steps)],
                           capture_output=True, text=True, timeout=1800)
        if r.returncode:
            raise RuntimeError('agx_run failed: '+(r.stdout+r.stderr)[-300:])
        return list(struct.unpack(f'<{words}I', (t/'r.bin').read_bytes())), json.loads(r.stdout.strip().splitlines()[-1])


def oracle_ok(out, count, want):
    rounded, words = layout(count)
    w = want if isinstance(want, list) else [want]*count
    return (len(out) == words and out[:8] == [GUARD]*8 and out[8:8+count] == w
            and out[8+count:8+rounded+8] == [GUARD]*(rounded-count+8) and out[-16:] == [TAIL+i for i in range(16)])


def require(code, count, want, **kw):
    if code[-2:] != b'\x88\x00':
        raise RuntimeError('refusing: program does not end with stop')
    out, stats = simulate(code, count, **kw)
    if not oracle_ok(out, count, want):
        raise RuntimeError('refusing: simulator output does not match the oracle')
    return {'oracle_ok': True, 'count': count, 'stats': stats}
