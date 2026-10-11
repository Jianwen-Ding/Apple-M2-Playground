#!/usr/bin/env python3
"""Metal-style shader capture for Asahi Mesa: run a program, capture every AGX binary Mesa
compiled, disassemble it and annotate it with the agx_cost.py cycle model.

    python3 scripts/agx_capture.py [options] -- <command ...>       # run + capture
    python3 scripts/agx_capture.py --cache DIR                      # analyse an existing cache dir
    python3 scripts/agx_capture.py --blob FILE [FILE ...]           # Vulkan VK_EXT_shader_object export,
                                                                    # or a decompressed cache blob

How it works (details: docs/shader-capture.md)
  1. The command runs with MESA_SHADER_CACHE_DIR=<out>/cache, MESA_SHADER_CACHE_DISABLE=false
     and every *_MESA_DEBUG variable removed (AGX_MESA_DEBUG disables the disk cache).
  2. Cache items are parsed exactly as Mesa writes them (src/util/mesa_cache_db.c entry header,
     src/util/disk_cache_os.c create_cache_item_header_and_blob: driver keys, item type,
     {crc32, uncompressed_size}, zstd frame) and decompressed with /usr/bin/zstd.
  3. Each payload is parsed as an Asahi Gallium shader blob (agx_disk_cache.c write_shader:
     agx_shader_info, binary, uvs, attrib mask, epilog key, push ranges, [GS children]) or a
     honeykrisp blob (hk_shader.c hk_api_shader_serialize: stage byte, then per variant
     hk_shader_info, agx_shader_info, code_size, data_size, code, data). A parse is accepted only
     if it consumes the payload exactly. Struct sizes/offsets come from tests/agx_cache_layout.c.
  4. agx_shader_info gives rodata / main / preamble offsets and sizes; each code region is
     disassembled with applegpu (Mesa's stack_adjust special-cased) and run through
     agx_cost.decode/trace/simulate for 1 and 4 SIMD groups per core.

Options: --out DIR (default /scratch/apple-m2-playground/capture/<utc>), --json FILE,
--ir (extra run with AGX_MESA_DEBUG=shaders, cache disabled, to attach Mesa's NIR/AGX IR),
--groups 1,4, --path auto|static|emulate, --loop-trips N, --timeout 60, --mesa auto|25.1|25.3.
SAFETY: only use with programs that go through Mesa's own GLES/Vulkan drivers.
"""
import argparse, datetime, json, os, re, struct, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agx_loop

REPO = Path(__file__).resolve().parents[1]
SCRATCH = Path('/scratch/apple-m2-playground/capture')

# ---- struct layouts (printed by tests/agx_cache_layout.c; aarch64 LP64) -------------------------
_FIELDS = {'stage': (0, 'i'), 'binary_size': (4, 'I'), 'push_count': (1044, 'H'), 'local_size': (1046, 'H'),
           'imageblock_stride': (1048, 'H'), 'scratch_size': (1052, 'I'), 'preamble_scratch_size': (1056, 'I'),
           'main_size': (1060, 'I'), 'has_preamble': (1064, 'B'), 'preamble_offset': (1068, 'I'),
           'main_offset': (1072, 'I'), 'reads_tib': (1076, 'B'), 'uses_txf': (1092, 'B'),
           'nr_gprs': (1094, 'H'), 'nr_preamble_gprs': (1096, 'H'), 'outputs': (1104, 'Q'),
           'workgroup_size': (1112, '3H'), 'rodata': (1120, 'IHH'), 'stats': (1128, '5I2HIH2x3I')}
LAYOUTS = {
    '25.1': dict(info_size=1176, uvs=88, attrib=8, epilog=4, push=6, gs_info=16, hk_info=664, gs_variants=7,
                 fields=_FIELDS),
    '25.3': dict(info_size=1176, uvs=88, attrib=8, epilog=4, push=6, gs_info=84, hk_info=976, gs_variants=4,
                 fields=dict(_FIELDS, nr_gprs=(1096, 'H'), nr_preamble_gprs=(1098, 'H'),
                             stats=(1128, '5I2HIH2x4I'))),
}
STATS = ['instrs', 'alu_cycles', 'fscib_cycles', 'ic_cycles', 'code_size', 'gprs', 'uniforms', 'scratch',
         'threads', 'loops', 'spills', 'fills', 'preamble_instrs']
STAGES = {0: 'vertex', 1: 'tess_ctrl', 2: 'tess_eval', 3: 'geometry', 4: 'fragment', 5: 'compute', 6: 'task',
          7: 'mesh', 14: 'kernel'}
HK_VARIANTS = {'25.1': {0: ['hw', 'sw'], 2: ['hw', 'sw'],
                        3: ['rast', 'main', 'main_no_rast', 'count', 'count_no_rast', 'pre', 'pre_no_rast']},
               '25.3': {0: ['hw', 'sw'], 2: ['hw', 'sw'], 3: ['rast', 'main', 'count', 'pre']}}
ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
VK_MAGIC = b'MesaVkShaderBin\x00'
VK_HEADER = 72          # struct vk_shader_bin_header (src/vulkan/runtime/vk_shader.c)


def installed_versions():
    """Mesa versions of the installed GL (libgallium-X.Y.Z.so) and Vulkan (libvulkan_asahi.so) drivers."""
    out = {}
    g = sorted(Path('/usr/lib64').glob('libgallium-*.so'))
    if g: out['gl'] = re.search(r'libgallium-(\d+\.\d+\.\d+)', g[-1].name).group(1)
    vk = Path('/usr/lib64/libvulkan_asahi.so')
    if vk.exists():
        m = re.search(rb'Mesa (\d+\.\d+\.\d+)', vk.read_bytes())
        if m: out['vulkan'] = m.group(1).decode()
    return out


def layout_for(version):
    return '25.3' if version and tuple(map(int, version.split('.')[:2])) >= (25, 3) else '25.1'


# ---- cache container parsing --------------------------------------------------------------------
def cache_items(cache):
    """Yield (source, key_hex, item_bytes) for every entry in a Mesa disk-cache directory
    (database format: mesa_shader_cache_db/part*/mesa_cache.db; multi-file: <2 hex>/<38 hex>)."""
    for db in sorted(Path(cache).rglob('mesa_cache.db'), key=lambda p: (len(str(p)), str(p))):
        b = db.read_bytes()
        if b[:8] != b'MESA_DB\x00': continue
        p = 20                                   # mesa_db_file_header: magic[8], version u32, uuid u64
        while p + 28 <= len(b):                  # mesa_cache_db_file_entry: key[20], crc u32, size u32
            key = b[p:p+20]; _crc, size = struct.unpack_from('<II', b, p+20)
            if size == 0 or p + 28 + size > len(b): break
            yield f'{db.parent.name}/{db.name}@{p}', key.hex(), b[p+28:p+28+size]
            p += 28 + size
    for f in sorted(Path(cache).rglob('*')):
        if f.is_file() and re.fullmatch(r'[0-9a-f]{38}', f.name) and re.fullmatch(r'[0-9a-f]{2}', f.parent.name):
            yield f'{f.parent.name}/{f.name}', f.parent.name + f.name, f.read_bytes()


def item_payload(item):
    """Cache item -> (item_type, gpu_name, uncompressed payload). Layout from create_cache_item_header_and_blob:
    cache_version u8, driver_id\\0, gpu_name\\0, ptr_size u8, driver_flags u64, (align 4) type u32,
    [GLSL: num_keys u32 + keys], cache_entry_file_data {crc32, uncompressed_size}, zstd data."""
    p = 1
    e = item.index(b'\0', p); p = e + 1
    e = item.index(b'\0', p); gpu = item[p:e].decode(errors='replace'); p = e + 1 + 1 + 8
    p = align4(p)                                # blob_write_uint32 aligns (src/util/blob.c)
    typ, = struct.unpack_from('<I', item, p); p += 4
    if typ == 1:
        nk, = struct.unpack_from('<I', item, p); p += 4 + 20*nk
    _crc, usize = struct.unpack_from('<II', item, p); p += 8
    body = item[p:]
    if body[:4] == ZSTD_MAGIC:
        z = subprocess.run(['zstd', '-d', '-q', '-c'], input=body, capture_output=True)
        if z.returncode or len(z.stdout) != usize:
            raise ValueError(f'zstd failed / size mismatch ({len(z.stdout)} != {usize})')
        body = z.stdout
    elif len(body) != usize:
        raise ValueError('unknown compression')
    return typ, gpu, body


# ---- shader blob parsing ------------------------------------------------------------------------
def read_info(d, o, L):
    info = {}
    for k, (off, fmt) in L['fields'].items():
        v = struct.unpack_from('<' + fmt, d, o + off)
        info[k] = v[0] if len(v) == 1 else list(v)
    info['rodata'] = dict(zip(['offset', 'base_uniform', 'size_16'], info['rodata']))
    info['stats'] = dict(zip(STATS, info['stats']))
    info['stage_name'] = STAGES.get(info['stage'], str(info['stage']))
    return info


def plausible(info):
    n = info['binary_size']
    return (info['stage'] in STAGES and 0 < n < (1 << 24) and info['main_offset'] < n
            and info['main_offset'] + info['main_size'] <= n
            and (not info['has_preamble'] or info['preamble_offset'] < n))


def align4(x):
    return (x + 3) & ~3


def parse_gallium(d, L, o=0, root=True, role='main'):
    """agx_disk_cache.c write_shader(). Returns (shaders, end offset) or raises."""
    info = read_info(d, o, L)
    if not plausible(info): raise ValueError('implausible agx_shader_info')
    p = o + L['info_size']; binary = d[p:p+info['binary_size']]; p += info['binary_size']
    p += L['uvs'] + L['attrib'] + L['epilog']
    p = align4(p); nr, = struct.unpack_from('<I', d, p); p += 4       # blob_write_uint32 aligns to 4
    if nr > 512: raise ValueError('push_range_count')
    p += L['push'] * nr
    out = [dict(role=role, info=info, binary=binary, push_ranges=nr)]
    if root and info['stage'] == 3:
        p += L['gs_info']
        sub, p = parse_gallium(d, L, p, False, 'pre_gs'); out += sub
        for name in ('gs_copy', 'gs_count'):
            has = d[p]; p += 1
            if has:
                sub, p = parse_gallium(d, L, p, False, name); out += sub
    return out, p


def parse_honeykrisp(d, L, version):
    """hk_shader.c hk_api_shader_serialize(), optionally behind a vk_shader_bin_header."""
    start = VK_HEADER if d[:16] == VK_MAGIC else 0
    stage = d[start]; names = HK_VARIANTS[version].get(stage, ['main'])
    p = start + 1; out = []
    for name in names:
        p += L['hk_info']
        info = read_info(d, p, L); p += L['info_size']
        p = align4(p); code_size, data_size = struct.unpack_from('<II', d, p); p += 8
        if code_size == 0 and data_size == 0:
            continue                                           # unused variant
        info['binary_size'] = code_size                        # hk_deserialize_shader does the same
        if not plausible(info): raise ValueError('implausible agx_shader_info')
        out.append(dict(role=f'variant:{name}', info=info, binary=d[p:p+code_size], data_size=data_size))
        p += code_size + data_size
    if p != len(d): raise ValueError(f'honeykrisp parse ended at {p} of {len(d)}')
    return out


def parse_blob(d, versions):
    """Try Gallium then honeykrisp layouts; a parse must consume the blob exactly."""
    errs = []
    for api in ('gl', 'vulkan') if d[:16] != VK_MAGIC else ('vulkan',):
        v = layout_for(versions.get(api)); L = LAYOUTS[v]
        try:
            if api == 'gl':
                sh, end = parse_gallium(d, L)
                if end != len(d): raise ValueError(f'gallium parse ended at {end} of {len(d)}')
            else:
                sh = parse_honeykrisp(d, L, v)
            for s in sh: s['format'] = f'{api} (Mesa {v} layout)'
            return sh
        except (ValueError, IndexError, struct.error) as e:
            errs.append(f'{api}: {e}')
    raise ValueError('; '.join(errs))


# ---- regions, disassembly, cost -----------------------------------------------------------------
def regions(sh):
    """Split the binary into rodata / main / preamble using agx_shader_info (agx_compile.c:
    rodata is packed before the code of the main function, every function is 128-byte aligned)."""
    i = sh['info']; n = len(sh['binary'])
    starts = [('main', i['main_offset'])]
    if i['has_preamble']: starts.append(('preamble', i['preamble_offset']))
    out = []
    for name, s in starts:
        if name == 'main':
            e = s + i['main_size']
        else:
            later = [x for _, x in starts if x > s] + ([i['rodata']['offset']] if i['rodata']['size_16'] and i['rodata']['offset'] > s else [])
            e = min(later) if later else n
        out.append((name, s, e))
    out.sort(key=lambda r: r[1])
    return out


def is_stack_adjust(raw, size):
    """Mesa agx_pack.c AGX_OPCODE_STACK_ADJUST: exact 0x10100b5 in bits 0..25 with the stack size
    spliced into bits 20..23, 32..35, 56..63, plus fixed i1=1 @26, i2=2 @36, bit 47."""
    return (size == 8 and raw & (((1 << 26)-1) & ~(0xf << 20)) == 0x10100b5 and (raw >> 26) & 3 == 1
            and (raw >> 36) & 0xff == 2 and (raw >> 47) & 1 and not (raw >> 44) & 7 and not (raw >> 8) & 0xff)


def disassemble(code):
    """-> list of {pc, size, hex, text, name}; stops at the last `stop` (Mesa pads with nops)."""
    _, g = agx_loop._tools()
    out, pc = [], 0
    while pc < len(code):
        n = g.opcode_to_number(code[pc:pc+16]); d = g.get_instruction_descriptor(n)
        if d is None:
            out.append(dict(pc=pc, size=2, hex=code[pc:pc+2].hex(), text='<undecodable>', name='?')); break
        size = d.decode_size(n); n &= (1 << 8*size) - 1
        text = ' '.join(str(d.disassemble(n)).split()); name = d.name
        if name == 'stack_store' and is_stack_adjust(n, size):
            words = (n >> 20 & 0xf) | (n >> 32 & 0xf) << 4 | (n >> 56) << 8
            name = 'stack_adjust'; text = f'stack_adjust #{words} (words; applegpu: {text})'
        out.append(dict(pc=pc, size=size, hex=code[pc:pc+size].hex(), text=text, name=name))
        pc += size
    last = max((k for k, r in enumerate(out) if r['name'] == 'stop'), default=len(out)-1)
    return out[:last+1], len(out) - last - 1


_P = None


def loops_in(code, ins):
    """Backward jmp_exec_any/none branches -> [(target_pc, branch_pc)]."""
    _, g = agx_loop._tools(); out = []
    for r in ins:
        if r['name'] in ('jmp_exec_any', 'jmp_exec_none'):
            n = g.opcode_to_number(code[r['pc']:r['pc']+16]); d = g.get_instruction_descriptor(n)
            off = dict(d.decode_fields(n & ((1 << 8*r['size'])-1)))['off']
            if off & (1 << 31): out.append((r['pc'] + off - (1 << 32), r['pc']))
    return out


def unrolled(static, loops, trips):
    """Straight-line path with every backward-branch body [target, branch] executed `trips` times
    (innermost first, so an outer body that contains an expanded inner loop multiplies it)."""
    pcs = list(static)
    for t, b in sorted(loops, key=lambda x: x[1] - x[0], reverse=False):
        i, j = pcs.index(t), pcs.index(b)
        pcs = pcs[:j+1] + pcs[i:j+1] * (trips - 1) + pcs[j+1:]
    return pcs


def cost(code, groups, path_mode, loop_trips=None):
    """Run agx_cost on one region. Returns dict (cycles per group count, per-pc stats) or {'error'}."""
    global _P
    try:
        import agx_cost
        if _P is None: _P = agx_cost.Params()
        ins = agx_cost.decode(code, _P)
        static = [r['pc'] for r in ins]
        loops = loops_in(code, ins)
        mode = path_mode if path_mode != 'auto' else ('emulate' if loops else 'static')
        if loop_trips and loops: mode = f'static, {len(loops)} loop(s) x{loop_trips}'
        skipped = []
        pcs = unrolled(static, loops, loop_trips) if loop_trips else static
        if mode == 'emulate':
            try:
                pcs, sk = agx_cost.trace(code); skipped = sorted(sk)
            except Exception as e:                          # emulator limits: fall back to one pass
                mode = f'static (emulate failed: {e})'; pcs = static
        res = {'path': mode, 'dynamic_instructions': len(pcs), 'emulator_skipped': skipped, 'cycles': {}, 'per_pc': {}}
        for G in groups:
            cyc, st = agx_cost.simulate(ins, pcs, _P, G, detail=True)
            res['cycles'][G] = cyc
            for pc, s in st.items():
                res['per_pc'].setdefault(pc, {})[G] = {'n': s['n'], 'stall': s['stall']}
        res['class'] = {r['pc']: (r.get('unit') or r.get('kind')) for r in ins}
        return res
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


# ---- IR dump (optional) -------------------------------------------------------------------------
def ir_sections(text):
    """Split an AGX_MESA_DEBUG=shaders dump into per-shader sections (NIR, then AGX IR before and
    after register allocation). A section ends at the first line that does not look like IR."""
    ir_line = re.compile(r'^(\s|$|\}|block\d+ \{|shader: |decl_|impl |[a-z_0-9]+: |\d+ = |r\d)')
    secs, cur = [], None
    for line in text.splitlines():
        if line.startswith('shader: MESA_SHADER_'):
            cur = dict(stage=line.split('MESA_SHADER_')[1].strip().lower(), workgroup_size=None, lines=[])
            secs.append(cur)
        elif cur is not None and not ir_line.match(line):
            cur = None
        if cur is not None:
            cur['lines'].append(line)
            m = re.match(r'workgroup_size: (\d+), (\d+), (\d+)', line)
            if m and cur['workgroup_size'] is None: cur['workgroup_size'] = [int(x) for x in m.groups()]
    return [dict(stage=c['stage'], workgroup_size=c['workgroup_size'], text='\n'.join(c['lines']).rstrip()) for c in secs]


# ---- main ---------------------------------------------------------------------------------------
def analyse(shaders, groups, path_mode, outdir, loop_trips=None):
    for k, sh in enumerate(shaders):
        sh['regions'] = []
        for name, s, e in regions(sh):
            raw = sh['binary'][s:e]
            listing, pad = disassemble(raw)
            code = raw[:sum(r['size'] for r in listing)]
            fn = outdir / f'shader{k}-{name}.bin'; fn.write_bytes(code)
            c = cost(code, groups, path_mode, loop_trips)
            for r in listing:
                if 'per_pc' in c:
                    r['class'] = c['class'].get(r['pc']); r['sim'] = c['per_pc'].get(r['pc'], {})
            sh['regions'].append(dict(name=name, offset=s, bytes=len(code), padding_instructions=pad,
                                      file=str(fn), listing=listing,
                                      cost={k2: v for k2, v in c.items() if k2 not in ('per_pc', 'class')}))


def render(shaders, groups):
    L = []
    for k, sh in enumerate(shaders):
        i = sh['info']
        L.append('=' * 100)
        kind = sh.get('kind', '')
        L.append(f"shader {k}: {i['stage_name']} {sh['role']}  [{sh['format']}]  {kind}")
        L.append(f"  source {sh['source']}  binary {i['binary_size']} B  main @{i['main_offset']}+{i['main_size']}"
                 + (f"  preamble @{i['preamble_offset']}" if i['has_preamble'] else '')
                 + (f"  rodata @{i['rodata']['offset']} {2*i['rodata']['size_16']} B -> u{i['rodata']['base_uniform']}" if i['rodata']['size_16'] else ''))
        L.append(f"  gprs(16-bit) main {i['nr_gprs']} preamble {i['nr_preamble_gprs']}  push uniforms {i['push_count']}"
                 f"  stack {i['scratch_size']}/{i['preamble_scratch_size']} words  local {i['local_size']} B  wg {i['workgroup_size']}")
        s = i['stats']
        L.append(f"  Mesa stats: instrs {s['instrs']}  alu {s['alu_cycles']}  fscib {s['fscib_cycles']}  ic {s['ic_cycles']}"
                 f"  threads {s['threads']}  loops {s['loops']}  spills {s['spills']}  fills {s['fills']}")
        if sh.get('ir'): L.append(f"  Mesa IR: matched AGX_MESA_DEBUG=shaders section ({len(sh['ir'].splitlines())} lines, in JSON)")
        for r in sh['regions']:
            c = r['cost']
            L.append(f"  --- {r['name']} @{r['offset']}  {r['bytes']} B  {len(r['listing'])} instructions"
                     + (f" (+{r['padding_instructions']} padding)" if r['padding_instructions'] else ''))
            if 'error' in c:
                L.append(f"      cost model unavailable: {c['error']}")
            else:
                L.append('      predicted cycles: ' + '  '.join(f"{G} group{'s' if G > 1 else ''}/core = {c['cycles'][G]}" for G in groups)
                         + f"   (path {c['path']}, {c['dynamic_instructions']} dynamic instrs"
                         + (f", emulator skipped {','.join(c['emulator_skipped'])}" if c['emulator_skipped'] else '') + ')')
            hdr = f"      {'pc':>5}  {'hex':<24} {'class':<14}" + ''.join(f" {'n@'+str(G):>5} {'stall@'+str(G):>8}" for G in groups) + '  disassembly'
            L.append(hdr)
            for x in r['listing']:
                sim = x.get('sim', {})
                cols = ''.join(f" {sim[G]['n'] if G in sim else '-':>5} {sim[G]['stall'] if G in sim else '-':>8}" for G in groups)
                L.append(f"      {x['pc']:5d}  {x['hex']:<24} {str(x.get('class') or ''):<14}{cols}  {x['text']}")
    return '\n'.join(L)


def clean_env(extra):
    env = {k: v for k, v in os.environ.items()
           if not (k.endswith('_MESA_DEBUG') or k.startswith('MESA_SHADER_CACHE') or k.startswith('MESA_DISK_CACHE')
                   or k == 'MESA_GLSL_CACHE_DISABLE')}
    env.update(extra)
    return env


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--json', type=Path)
    ap.add_argument('--cache', type=Path, help='analyse an existing MESA_SHADER_CACHE_DIR instead of running')
    ap.add_argument('--blob', type=Path, nargs='+', help='analyse shader blobs (Vulkan shader-object export or raw)')
    ap.add_argument('--ir', action='store_true', help='extra run with AGX_MESA_DEBUG=shaders to attach Mesa IR')
    ap.add_argument('--groups', default='1,4')
    ap.add_argument('--path', choices=['auto', 'static', 'emulate'], default='auto')
    ap.add_argument('--loop-trips', type=int, help='assume every loop runs N times (static path) instead of emulating')
    ap.add_argument('--timeout', type=int, default=60)
    ap.add_argument('--cwd', type=Path, help='working directory for the command (default: <out>/run)')
    ap.add_argument('--mesa', default='auto', help='layout: auto (installed drivers), 25.1 or 25.3')
    ap.add_argument('--quiet', action='store_true', help='do not print the listing')
    ap.add_argument('cmd', nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ['--'] else a.cmd
    if not (cmd or a.cache or a.blob): ap.error('give -- <command>, --cache or --blob')
    groups = [int(x) for x in a.groups.split(',')]
    versions = installed_versions() if a.mesa == 'auto' else {'gl': a.mesa + '.0', 'vulkan': a.mesa + '.0'}
    out = (a.out or SCRATCH / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {'command': cmd, 'out': str(out), 'mesa_versions': versions, 'runs': [], 'skipped_items': []}
    shaders = []

    if cmd:
        cache = out / 'cache'
        subprocess.run(['rm', '-rf', str(cache)], check=True); cache.mkdir()
        cwd = a.cwd or out / 'run'; cwd.mkdir(exist_ok=True)     # programs may write files to cwd
        env = clean_env({'MESA_SHADER_CACHE_DIR': str(cache), 'MESA_SHADER_CACHE_DISABLE': 'false'})
        try:
            r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=a.timeout)
            rc, so, se = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            rc, so, se = 'timeout', e.stdout or b'', e.stderr or b''
        (out/'stdout.txt').write_bytes(so); (out/'stderr.txt').write_bytes(se)
        report['runs'].append({'kind': 'capture', 'returncode': rc})
        print(f'[capture] command exit {rc}; cache {cache}', file=sys.stderr)
        a.cache = cache
        if a.ir:
            env = clean_env({'MESA_SHADER_CACHE_DISABLE': 'true', 'AGX_MESA_DEBUG': 'shaders'})
            try:
                r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=a.timeout)
                rc, so = r.returncode, r.stdout
            except subprocess.TimeoutExpired as e:
                rc, so = 'timeout', e.stdout or b''
            (out/'ir-dump.txt').write_bytes(so)
            report['runs'].append({'kind': 'ir-dump', 'returncode': rc})

    if a.cache:
        for src, key, item in cache_items(a.cache):
            try:
                typ, gpu, payload = item_payload(item)
                if typ == 1: report['skipped_items'].append({'source': src, 'reason': 'GLSL program metadata'}); continue
                sh = parse_blob(payload, versions)
            except (ValueError, IndexError, struct.error) as e:
                report['skipped_items'].append({'source': src, 'reason': str(e)[:200]}); continue
            for s in sh: s.update(source=src, cache_key=key, gpu=gpu)
            shaders += sh
    for f in a.blob or []:
        d = f.read_bytes()
        if d[:4] == ZSTD_MAGIC:
            d = subprocess.run(['zstd', '-d', '-q', '-c'], input=d, capture_output=True, check=True).stdout
        try:
            sh = parse_blob(d, versions)
        except (ValueError, IndexError, struct.error) as e:
            report['skipped_items'].append({'source': str(f), 'reason': str(e)[:200]}); continue
        for s in sh: s.update(source=str(f))
        shaders += sh

    if (out/'ir-dump.txt').exists() and a.ir:
        secs = ir_sections((out/'ir-dump.txt').read_text(errors='replace'))
        used = set()
        for sh in shaders:
            i = sh['info']
            for j, s in enumerate(secs):
                if j in used or s['stage'] != i['stage_name']: continue
                if i['stage'] == 5 and s['workgroup_size'] and s['workgroup_size'] != i['workgroup_size']: continue
                sh['ir'] = s['text']; sh['kind'] = 'application shader'; used.add(j); break
            else:
                sh['kind'] = 'driver-internal? (not in AGX_MESA_DEBUG=shaders dump)'

    analyse(shaders, groups, a.path, out, a.loop_trips)
    text = render(shaders, groups)
    (out/'listing.txt').write_text(text + '\n')
    if not a.quiet: print(text)
    print(f"[capture] {len(shaders)} shader(s), {len(report['skipped_items'])} other cache item(s); listing {out/'listing.txt'}",
          file=sys.stderr)
    for s in shaders:
        s['binary_hex'] = s.pop('binary').hex()
    report['shaders'] = shaders
    js = a.json or out / 'capture.json'
    js.write_text(json.dumps(report, indent=1, default=str) + '\n')
    print(f'[capture] json {js}', file=sys.stderr)
    return 0 if shaders else 1


if __name__ == '__main__':
    sys.exit(main())
