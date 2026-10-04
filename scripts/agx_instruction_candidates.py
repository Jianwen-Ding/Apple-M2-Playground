#!/usr/bin/env python3
"""Export bounded OFFLINE AGX ALU candidates; never patch or submit a shader."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MASK32 = (1 << 32) - 1
INPUTS = [0, 1, 0x7fffffff, 0x80000000, 0xffffffff, 0x12345678]
CASES = [
    ('mov-small', 'mov_imm', (1,), (2,)),
    ('mov-bit0', 'mov_imm', (0x12345678,), (0x12345679,)),
    ('add-small', 'iadd', (1,), (2,)),
    ('add-split-immediate', 'iadd', (63,), (64,)),
    ('mul-low-coefficient', 'imadd', (2, 0), (3, 0)),
    ('mad-addend', 'imadd', (2, 0), (2, 1)),
]


def mesa_bits(op, immediates, dst, src):
    """Restricted translation of agx_pack.c; not Mesa's compiled encoder.

    32-bit destination, ordinary uncached registers, unsigned/zero-extended
    source (Mesa .abs=true), no saturation/negation/shift, low register indices.
    Mesa register values count 16-bit halves; applegpu rN counts 32-bit words.
    """
    opcode = {'mov_imm': 0x62, 'iadd': 0x0e, 'imadd': 0x1e}[op]
    dest = 2 | ((2*dst) << 2)
    raw = opcode | ((dest & 255) << 7)
    if op == 'mov_imm':
        return (raw | (immediates[0] << 16)).to_bytes(6, 'little')
    sources = [(2*src) | (1 << 6) | (2 << 8)]
    sources += [(value & 63) | ((value >> 6) << 10) for value in immediates]
    extend = 0
    for index, value in enumerate(sources):
        raw |= (value & 1023) << (16 + 12*index)
        extend |= (value >> 10) << (16 - (index+3)*2)
    raw |= extend << (32 if op == 'iadd' else 48)
    return raw.to_bytes(8, 'little')


def host_result(op, imm, x):
    if op == 'mov_imm':
        return imm[0]
    if op == 'iadd':
        return (x + imm[0]) & MASK32
    return (x*imm[0] + imm[1]) & MASK32


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--applegpu-root', type=Path, default=Path(os.environ.get('APPLEGPU_ROOT', '/save/workspace/AGX_Probe/applegpu')))
    parser.add_argument('--mesa-root', type=Path, default=Path(os.environ.get('MESA_ROOT', '/save/workspace/AGX_Probe/mesa')))
    parser.add_argument('--dst-r32', type=int, default=0)
    parser.add_argument('--src-r32', type=int, default=1)
    parser.add_argument('--output', type=Path, help='write candidate JSON; otherwise stdout')
    args = parser.parse_args()
    args.applegpu_root = args.applegpu_root.expanduser().resolve()
    args.mesa_root = args.mesa_root.expanduser().resolve()
    if sys.flags.optimize:
        parser.error("run without -O: offline consistency assertions are required")
    if not (0 <= args.dst_r32 < 32 and 0 <= args.src_r32 < 32) or args.dst_r32 == args.src_r32:
        parser.error('use distinct low 32-bit registers 0..31; no register extension')
    # Avoid generating __pycache__ in the read-only vendor checkout.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.applegpu_root.resolve()))
    gpu = importlib.import_module('applegpu')
    assembler = importlib.import_module('assemble')
    for module, filename in [(gpu, 'applegpu.py'), (assembler, 'assemble.py')]:
        if Path(module.__file__).resolve() != args.applegpu_root / filename:
            parser.error('imported module does not match configured applegpu reference root')
    pack = args.mesa_root/'src/asahi/compiler/agx_pack.c'
    opcodes = args.mesa_root/'src/asahi/compiler/agx_opcodes.py'
    opcode_text = opcodes.read_text()
    for name, value in [('mov_imm',0x62),('iadd',0x0e),('imad',0x1e)]:
        assert re.search(r'op\("'+name+r'", encoding = \(0x'+format(value,'02X')+r',', opcode_text, re.I), name
    pack_text = pack.read_text()
    for fragment in ['unsigned offset = 16 + (12 * s);',
                     'raw |= (uint64_t)(I->imm) << 16;',
                     'raw |= (D & BITFIELD_MASK(8)) << 7;',
                     'extend_offset -= 16;',
                     'unsigned hint = src.discard ? 0x3 : src.cache ? 0x2 : 0x1;',
                     'bool zext = I->src[s].abs || I->src[s].type == AGX_INDEX_IMMEDIATE;']:
        assert fragment in pack_text, 'Mesa transcription needs review: '+fragment
    def text(op, immediates):
        operands = [f'r{args.dst_r32}']
        if op != 'mov_imm':
            operands.append(f'r{args.src_r32}')
        operands += [str(v) for v in immediates]
        if op == 'mov_imm':
            operands.append('0')  # Explicit helper-kill bit; assembler has no default.
        return op+' '+', '.join(operands)
    def encode(op, imm):
        assembly = text(op, imm)
        data = bytes(assembler.assemble_line(assembly))
        assert data == mesa_bits(op,imm,args.dst_r32,args.src_r32), assembly
        number = gpu.opcode_to_number(data)
        descriptor = next(d for d in gpu.instruction_descriptors if d.matches(number))
        assert descriptor.decode_size(number) == len(data)
        assert descriptor.decode_remainder(number) == 0
        return {'assembly':assembly,'bytes_le_hex':data.hex(),
                'decoder_text':str(descriptor.disassemble(number)).strip(),
                'decoder_fields':dict(descriptor.decode_fields(number))}, data
    candidates = []
    for name, op, before, after in CASES:
        baseline, b = encode(op,before)
        modified, m = encode(op,after)
        assert len(b) == len(m)
        xor = int.from_bytes(b,'little') ^ int.from_bytes(m,'little')
        # Only immediate value fields may change: B low bits/extension or C.
        allowed = ((MASK32 << 16) if op=='mov_imm' else
                   ((63 << 28) | (3 << 40)) if op=='iadd' else
                   ((63 << 28) | (3 << 56) | (63 << 40) | (3 << 54)))
        assert xor and not (xor & ~allowed)
        candidates.append({'id':name,'baseline':baseline,'modified':modified,
                           'size_bytes':len(b),'xor_le_hex':xor.to_bytes(len(b),'little').hex(),
                           'changed_bits_lsb0':[i for i in range(len(b)*8) if xor & (1 << i)],
                           'fixtures':[{'input_u32':x,'baseline_u32':host_result(op,before,x),
                                        'modified_u32':host_result(op,after,x)} for x in INPUTS]})
    def provenance(root, paths):
        process = subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,timeout=5)
        assert process.returncode==0
        return {'root':str(root.resolve()),'git_head':process.stdout.strip(),
                'sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    payload = {'status':'OFFLINE_CANDIDATES_ONLY','target_to_validate':'G14C B1',
               'hardware_execution_performed':False,
               'cross_check':'applegpu assembler vs independent transcription of Mesa source bitfields; not two built encoders',
               'oracle':'uint32 modulo 2^32 host arithmetic; no software emulator execution',
               'registers':{'dst_r32':args.dst_r32,'src_r32':args.src_r32,'source_zero_extended':True},
               'placement_constraints':[
                   'Template bytes are not offsets into an opaque shader container.',
                   'Locate one decoded matching baseline ALU instruction inside executable code; require full-byte match and compiler disassembly confirmation.',
                   'Prove destination is a live 32-bit arithmetic result feeding only the checked output data, never an address, bounds, loop count, lane mask or resource descriptor.',
                   'Prove source register is live initialized uint32 input; preserve physical registers, allocation metadata and all surrounding instructions.',
                   'Use only the immediate XOR; preserve opcode, length, shift, sign extension, saturation, cache/discard, helper-kill and control bits.',
                   'Same-size edits preserve subsequent offsets; leave branches, waits, stop/epilogue, memory operations and container metadata untouched.',
                   'Re-read decoder fields after editing; execute unchanged baseline and guarded readback control before/after each single variation.',
                   'Binary import/roundtrip and G14C validity must be established by the execution harness; local applegpu describes G13.'
               ],
               'sources':{'applegpu':provenance(args.applegpu_root,[args.applegpu_root/'applegpu.py',args.applegpu_root/'assemble.py']),
                          'mesa':provenance(args.mesa_root,[pack,opcodes])},'candidates':candidates}
    output = json.dumps(payload,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(output)
    else:
        print(output,end='')


if __name__ == '__main__':
    main()
