#!/usr/bin/env python3
"""Offline check of the retained Mesa stack-shader evidence (no GPU)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agx_loop
r = json.loads((Path(__file__).resolve().parents[1]/'results/2026-10-11-stack-via-mesa/record.json').read_text())
_, g = agx_loop._tools()
main = bytes.fromhex(r['main_hex'])
checks = [
    (r['outputs_exact'], 'all 64 outputs equal the host model (run through Mesa)'),
    (r['stack_words'] == 1036 and main[:8].hex() == r['stack_adjust_hex'], 'binary starts with Mesa stack_adjust #0x40c (4096 B / 4 + 10, aligned to 4)'),
    (main.endswith(b'\x88\x00'), 'binary ends with stop'),
    (sum(1 for x in r['disassembly'] if x[2].startswith('stack_store i32')) == 1 and sum(1 for x in r['disassembly'] if x[2].startswith('stack_load')) == 2,
     'one i32 stack_store and two stack_loads'),
    (r['disassembly'][0][2].startswith('stack_store i8'), 'applegpu decodes stack_adjust as an i8 stack_store (shared opcode 0xb5)'),
]
fails = 0
for ok, msg in checks:
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+msg)
print(f'{fails} failures'); sys.exit(1 if fails else 0)
