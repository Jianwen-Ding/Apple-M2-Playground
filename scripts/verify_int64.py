#!/usr/bin/env python3
"""Offline check of the retained 64-bit integer and pointer evidence (no GPU)."""
import gzip, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_drm_int64 as I

R = Path(__file__).resolve().parents[1]/'results/2026-10-11-int64'
st = json.loads(gzip.open(R/'int64-all.json.gz').read())
fails = 0
for name, (asm, model) in I.CASES.items():
    raw = st['cases'][name]['raw']
    bad = sum(I.p64(r[4], r[5]) != model(*r[:4]) for r in raw)
    ok = st['cases'][name]['asm'] == asm and len(raw) >= 400 and bad == 0
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+f'{name} ({asm}): {len(raw)} vectors, {bad} mismatches')
p = json.loads(gzip.open(R/'pointer.json.gz').read())
T = [w*7+3 for w in range(320)]
u = p['uniform_split']; ok = u['u8'] == u['va'] & 0xffffffff and u['u9'] == u['va'] >> 32
fails += not ok; print(('ok   ' if ok else 'FAIL ')+f"u8/u9 = low/high words of the table VA {u['va']:#x}")
for name, off in (('regbase+lane<<2', 0), ('regbase,index r1', 0), ('regbase+1024+sx(lane-64)<<2', 192)):
    ok = p['cases'][name]['out'] == [T[off+i] for i in range(64)]
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+f'pointer load {name}')
print(f'{fails} failures'); sys.exit(1 if fails else 0)
