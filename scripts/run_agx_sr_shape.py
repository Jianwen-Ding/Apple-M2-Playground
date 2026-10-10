#!/usr/bin/env python3
"""Special-register reads under varied workgroup shapes and 3-D dispatches.

For each (local size, group count) shape: encode SPIR-V that stores the
constant 0x12345678 at data[8 + linear index], where

    linear = LocalInvocationIndex + L * (wg.x + nx * (wg.y + ny * wg.z))

export Mesa's AGX binary and require an exact constant readback, then replace
that binary's unique `mov_imm rN, 0x12345678` with `get_sr rN, selector; wait 0`.
Every output word is therefore attributed to one (workgroup, local) coordinate.
Guards, padding and the patterned tail are checked on every readback.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys
import time

import run_vulkan_compute as baseline
from patch_agx_imadd import integrity, load_model

REPO = Path(__file__).resolve().parents[1]
CONSTANT = 0x12345678
APPLEGPU = Path('/save/workspace/AGX_Probe/applegpu')
# (local x,y,z), (groups x,y,z). Chosen so every lane has a distinct output slot.
SHAPES = [((32, 1, 1), (3, 1, 1)), ((8, 4, 1), (2, 3, 1)), ((4, 2, 4), (2, 2, 2)),
          ((16, 1, 1), (2, 1, 3)), ((64, 1, 1), (2, 1, 1)), ((24, 1, 1), (3, 1, 1)),
          ((7, 3, 2), (2, 2, 1)), ((128, 2, 1), (1, 1, 2)), ((1, 1, 1), (5, 2, 1))]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spirv(local, path, grammar):
    """Hand-encoded SPIR-V 1.3 by instruction schema (no compiler installed)."""
    schema = json.loads(grammar.read_text())
    ops = {i['opname']: i['opcode'] for i in schema['instructions']}
    enums = {k['kind']: {e['enumerant']: int(e['value'], 0) if isinstance(e['value'], str) else e['value']
                         for e in k.get('enumerants', [])} for k in schema['operand_kinds']}
    e = lambda kind, name: enums[kind][name]
    words = [0x07230203, 0x00010300, 0, 47, 0]
    def emit(name, *args):
        words.extend([((len(args)+1) << 16) | ops[name], *args])
    sc, bi, dec = 'StorageClass', 'BuiltIn', 'Decoration'
    emit('OpCapability', e('Capability', 'Shader'))
    emit('OpMemoryModel', e('AddressingModel', 'Logical'), e('MemoryModel', 'GLSL450'))
    emit('OpEntryPoint', e('ExecutionModel', 'GLCompute'), 24, 0x6e69616d, 0, 7, 8, 10)
    emit('OpExecutionMode', 24, e('ExecutionMode', 'LocalSize'), *local)
    emit('OpDecorate', 7, e(dec, 'BuiltIn'), e(bi, 'WorkgroupId'))
    emit('OpDecorate', 8, e(dec, 'BuiltIn'), e(bi, 'NumWorkgroups'))
    emit('OpDecorate', 10, e(dec, 'BuiltIn'), e(bi, 'LocalInvocationIndex'))
    emit('OpDecorate', 11, e(dec, 'ArrayStride'), 4)
    emit('OpDecorate', 12, e(dec, 'Block')); emit('OpMemberDecorate', 12, 0, e(dec, 'Offset'), 0)
    emit('OpDecorate', 14, e(dec, 'DescriptorSet'), 0); emit('OpDecorate', 14, e(dec, 'Binding'), 0)
    emit('OpDecorate', 16, e(dec, 'Block')); emit('OpMemberDecorate', 16, 0, e(dec, 'Offset'), 0)
    emit('OpTypeVoid', 1); emit('OpTypeInt', 2, 32, 0); emit('OpTypeBool', 3)
    emit('OpTypeVector', 4, 2, 3); emit('OpTypeFunction', 5, 1)
    emit('OpTypePointer', 6, e(sc, 'Input'), 4)
    emit('OpVariable', 6, 7, e(sc, 'Input')); emit('OpVariable', 6, 8, e(sc, 'Input'))
    emit('OpTypePointer', 9, e(sc, 'Input'), 2); emit('OpVariable', 9, 10, e(sc, 'Input'))
    emit('OpTypeRuntimeArray', 11, 2); emit('OpTypeStruct', 12, 11)
    emit('OpTypePointer', 13, e(sc, 'StorageBuffer'), 12); emit('OpVariable', 13, 14, e(sc, 'StorageBuffer'))
    emit('OpTypePointer', 15, e(sc, 'StorageBuffer'), 2)
    emit('OpTypeStruct', 16, 2); emit('OpTypePointer', 17, e(sc, 'PushConstant'), 16)
    emit('OpVariable', 17, 18, e(sc, 'PushConstant')); emit('OpTypePointer', 19, e(sc, 'PushConstant'), 2)
    for ident, value in [(20, 0), (21, 8), (22, CONSTANT), (23, local[0]*local[1]*local[2])]:
        emit('OpConstant', 2, ident, value)
    emit('OpFunction', 1, 24, 0, 5); emit('OpLabel', 25)
    emit('OpLoad', 4, 26, 7); emit('OpLoad', 4, 27, 8); emit('OpLoad', 2, 28, 10)
    emit('OpCompositeExtract', 2, 29, 26, 0); emit('OpCompositeExtract', 2, 30, 26, 1)
    emit('OpCompositeExtract', 2, 31, 26, 2); emit('OpCompositeExtract', 2, 32, 27, 0)
    emit('OpCompositeExtract', 2, 33, 27, 1)
    emit('OpIMul', 2, 34, 33, 31); emit('OpIAdd', 2, 35, 30, 34); emit('OpIMul', 2, 36, 32, 35)
    emit('OpIAdd', 2, 37, 29, 36); emit('OpIMul', 2, 38, 23, 37); emit('OpIAdd', 2, 39, 28, 38)
    emit('OpAccessChain', 19, 40, 18, 20); emit('OpLoad', 2, 41, 40)
    emit('OpULessThan', 3, 42, 39, 41); emit('OpSelectionMerge', 44, 0)
    emit('OpBranchConditional', 42, 43, 44); emit('OpLabel', 43)
    emit('OpIAdd', 2, 45, 39, 21); emit('OpAccessChain', 15, 46, 14, 20, 45)
    emit('OpStore', 46, 22); emit('OpBranch', 44); emit('OpLabel', 44)
    emit('OpReturn'); emit('OpFunctionEnd')
    path.write_bytes(struct.pack('<'+'I'*len(words), *words))
    return path


def patch(blob, selector, gpu):
    """Replace the unique mov_imm of CONSTANT with get_sr into the same register."""
    sites = [i for i in range(len(blob)-5) if blob[i] & 0x7f == 0x62 and blob[i+2:i+6] == CONSTANT.to_bytes(4, 'little')]
    if len(sites) != 1:
        raise ValueError(f'expected one mov_imm site, found {len(sites)}')
    site = sites[0]
    n = gpu.opcode_to_number(blob[site:])
    desc = gpu.get_instruction_descriptor(n)
    fields = dict(desc.decode_fields(n))
    if desc.name != 'mov_imm' or desc.decode_size(n) != 6 or fields.get('Dt') != 2:
        raise ValueError('constant site is not a 6-byte 32-bit mov_imm: '+str(fields))
    d = fields['D']
    raw = 0x72 | (2 << 7) | ((d & 63) << 9) | ((d >> 6) << 28) | ((selector & 63) << 16) | ((selector >> 6) << 26)
    sd = gpu.get_instruction_descriptor(raw)
    if type(sd).__name__ != 'MovFromSrInstructionDesc' or dict(sd.decode_fields(raw)) != {'Dt': 2, 'D': d, 'SR': selector}:
        raise ValueError('get_sr encoding mismatch')
    changed = bytearray(blob)
    changed[site:site+6] = raw.to_bytes(4, 'little') + bytes.fromhex('3800')
    changed[48:68] = integrity(changed)
    if blob[48:68] != integrity(blob):
        raise ValueError('input wrapper integrity mismatch')
    return bytes(changed), {'site': site, 'old': blob[site:site+6].hex(), 'new': changed[site:site+6].hex(),
                            'dest_half_reg': d, 'decoded': str(sd.disassemble(raw))}


def coordinates(local, groups):
    lx, ly, lz = local; gx, gy, gz = groups; L = lx*ly*lz
    out = []
    for wz in range(gz):
        for wy in range(gy):
            for wx in range(gx):
                for li in range(L):
                    out.append({'wg': (wx, wy, wz), 'lid': (li % lx, li//lx % ly, li//(lx*ly)), 'li': li})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selectors', default='0,1,2,4,5,6,7,8,9,10,15,19,24,25,48,49,50,51,52,53,56,57,58,59,80,81,82,97,114')
    p.add_argument('--shapes', default='all', help='all or comma-separated SHAPES indices')
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--output', type=Path)
    p.add_argument('--runtime', type=Path, default=Path('/scratch/apple-m2-playground/vulkan-runtime/usr/lib64'))
    p.add_argument('--grammar', type=Path, default=Path('/save/workspace/AGX_Probe/mesa/src/compiler/spirv/spirv.core.grammar.json'))
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    selectors = [int(s) for s in a.selectors.split(',')]
    shapes = SHAPES if a.shapes == 'all' else [SHAPES[int(i)] for i in a.shapes.split(',')]
    if not (1 <= a.repeats <= 5 and all(0 <= s <= 255 for s in selectors)):
        p.error('bounded repeats and selectors 0..255 required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/sr-shape-runs')/stamp
    out.mkdir(parents=True, exist_ok=False)
    state = {'passed': False, 'utc': stamp, 'selectors': selectors, 'repeats': a.repeats,
             'shapes': [], 'commands': [], 'failures': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('VK_', 'MESA_', 'ASAHI_', 'AGX_', 'HK_', 'LIBGL_', 'GALLIUM_', 'DRI_', 'LD_'))}
    child = env | {'VK_DRIVER_FILES': str(baseline.ICD), 'VK_ICD_FILENAMES': str(baseline.ICD),
                   'VK_LOADER_LAYERS_DISABLE': '~implicit~', 'LD_LIBRARY_PATH': str(a.runtime.resolve()),
                   'MESA_SHADER_CACHE_DISABLE': 'true'}
    def run(argv, seconds=15, child_env=child):
        cmd = {'argv': list(map(str, argv)), 'host_before_ns': time.monotonic_ns()}
        try:
            r = subprocess.run(cmd['argv'], env=child_env, capture_output=True, timeout=seconds)
            cmd['returncode'] = r.returncode; stdout = r.stdout; cmd['stderr'] = r.stderr.decode(errors='replace')[-2000:]
        except subprocess.TimeoutExpired:
            cmd['returncode'] = None; cmd['timed_out'] = True; stdout = b''
        cmd['host_after_ns'] = time.monotonic_ns(); state['commands'].append(cmd)
        if cmd['returncode'] != 0:
            raise RuntimeError('child failed: '+' '.join(cmd['argv'][:2])+' '+cmd.get('stderr', ''))
        return stdout
    def readback(path, count, words_expected=None):
        rounded = (count+31)//32*32
        data = path.read_bytes(); words = list(struct.unpack('<'+'I'*(len(data)//4), data))
        if len(words) != rounded+32: raise ValueError('readback size')
        initial = [0xcdcdcdcd]*(rounded+16)+[0xa5a50000+j for j in range(16)]
        untouched = list(range(8))+list(range(8+count, rounded+32))
        if any(words[i] != initial[i] for i in untouched): raise ValueError('guard/tail corruption')
        values = words[8:8+count]
        if words_expected is not None and values != words_expected: raise ValueError('oracle mismatch')
        return values, data
    try:
        if sha(baseline.DRIVER) != baseline.DRIVER_HASH: raise ValueError('driver hash changed')
        gpu, _ = load_model(APPLEGPU)
        sources = out/'sources'; sources.mkdir()
        for f in (Path(__file__), REPO/'tests/vulkan_compute.c'): shutil.copy2(f, sources/f.name)
        state['source_hashes'] = {f.name: sha(f) for f in (Path(__file__), REPO/'tests/vulkan_compute.c')}
        binary = out/'vulkan_compute'
        run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-I/save/workspace/AGX_Probe/mesa/include',
                               REPO/'tests/vulkan_compute.c', '-ldl', '-o', binary], 30, env)
        for k, (local, groups) in enumerate(shapes):
            tag = 'l%dx%dx%d-g%dx%dx%d' % (*local, *groups)
            count = local[0]*local[1]*local[2]*groups[0]*groups[1]*groups[2]
            shape = {'tag': tag, 'local': local, 'groups': groups, 'count': count, 'observations': {}}
            state['shapes'].append(shape)
            spv = spirv(local, out/(tag+'.spv'), a.grammar)
            v = json.loads(run([sys.executable, REPO/'scripts/run_vulkan_compute.py', '--validate', spv], 30, env))
            if v['result'] != 0: raise ValueError('SPIR-V validation failed: '+tag)
            exported = out/(tag+'.bin')
            dims = list(map(str, groups))
            run([binary, 'export', spv, count, '/dev/dri/renderD128', out/(tag+'-export.readback'), exported, *dims])
            readback(out/(tag+'-export.readback'), count, [CONSTANT]*count)
            blob = exported.read_bytes(); shape['export_sha256'] = sha(exported)
            run([binary, 'import', exported, count, '/dev/dri/renderD128', out/(tag+'-import.readback'), out/'unused.bin', *dims])
            readback(out/(tag+'-import.readback'), count, [CONSTANT]*count)
            for sel in selectors:
                patched, ev = patch(blob, sel, gpu)
                code = out/f'{tag}-sr{sel:03d}.bin'; code.write_bytes(patched)
                samples = []
                try:
                    for r in range(a.repeats):
                        rb = out/f'{tag}-sr{sel:03d}-r{r}.readback'
                        run([binary, 'import', code, count, '/dev/dri/renderD128', rb, out/'unused.bin', *dims])
                        samples.append(readback(rb, count)[0])
                except Exception as e:
                    state['failures'].append({'shape': tag, 'selector': sel, 'error': str(e)})
                    run([binary, 'import', exported, count, '/dev/dri/renderD128', out/'recovery.readback', out/'unused.bin', *dims])
                    readback(out/'recovery.readback', count, [CONSTANT]*count)
                shape['observations'][sel] = {'patch': ev, 'samples': samples}
            shape['patch_site'] = ev['site']; save()
            print(json.dumps({'shape': tag, 'failures': len(state['failures'])}), flush=True)
        state['passed'] = not state['failures']
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        save(); print(json.dumps({'passed': state['passed'], 'output': str(out), 'error': state.get('error')}))
    return 0 if state['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
