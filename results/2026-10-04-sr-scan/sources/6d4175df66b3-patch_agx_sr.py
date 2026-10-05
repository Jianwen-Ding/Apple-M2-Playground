#!/usr/bin/env python3
"""Pinned data-only special-register read probe. Unknown selectors are experimental."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from patch_agx_imadd import load_model, integrity, CODE_START, CODE_SIZE
from patch_agx_shader import CONTROL_SHA256

SITE = CODE_START + 0x96


def patch(blob, selector, root=Path('/save/workspace/AGX_Probe/applegpu')):
    if type(selector) is not int or not 0 <= selector <= 255:
        raise ValueError('selector must be an integer 0..255')
    if hashlib.sha256(blob).hexdigest() != CONTROL_SHA256:
        raise ValueError('unrecognized control binary')
    if (len(blob) != 2572 or blob[48:68] != integrity(blob) or
            struct.unpack_from('<II', blob, CODE_START - 8) != (CODE_SIZE, 0) or
            blob[SITE:SITE+6] != bytes.fromhex('620978563412')):
        raise ValueError('pinned layout mismatch')
    gpu, _ = load_model(root)
    # Dt=2: 32-bit ordinary destination. D=4: physical half-register r2.
    raw = 0x72 | (2 << 7) | (4 << 9) | ((selector & 63) << 16) | ((selector >> 6) << 26)
    read = raw.to_bytes(4, 'little')
    desc = gpu.get_instruction_descriptor(raw)
    if (type(desc).__name__ != 'MovFromSrInstructionDesc' or desc.decode_size(raw) != 4 or
            dict(desc.decode_fields(raw)) != {'Dt': 2, 'D': 4, 'SR': selector}):
        raise ValueError('special register decode mismatch')
    wait = bytes.fromhex('3800')
    wd = gpu.get_instruction_descriptor(int.from_bytes(wait, 'little'))
    if wd.name != 'wait' or wd.decode_size(int.from_bytes(wait, 'little')) != 2:
        raise ValueError('padding wait decode mismatch')
    changed = bytearray(blob)
    changed[SITE:SITE+6] = read + wait
    changed[48:68] = integrity(changed)
    changed = bytes(changed)
    offsets = [i for i,(a,b) in enumerate(zip(blob, changed)) if a != b]
    if any(not (48 <= i < 68 or SITE <= i < SITE + 6) for i in offsets):
        raise ValueError('unexpected mutation')
    return changed, {'selector': selector, 'site': SITE, 'old': blob[SITE:SITE+6].hex(),
                     'new': (read+wait).hex(), 'decoded': str(desc.disassemble(raw)),
                     'fields': dict(desc.decode_fields(raw)), 'changed_offsets': offsets,
                     'input_sha256': hashlib.sha256(blob).hexdigest(),
                     'patched_sha256': hashlib.sha256(changed).hexdigest(),
                     'wrapper_sha1': changed[48:68].hex()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--selector', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    blob, evidence = patch(a.input.read_bytes(), a.selector)
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'shader.bin').write_bytes(blob)
    (a.output / 'patch.json').write_text(json.dumps(evidence, indent=2)+'\n')


if __name__ == '__main__':
    main()
