#!/usr/bin/env python3
"""Offline check of the retained float-semantics evidence (no GPU).

Re-runs the exact host models over every stored (A, B, C, GPU result) and requires
that exactly the claimed model matches every lane, that the rejected models do not,
and that NaN results are canonical."""
import gzip, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_drm_float as F

R = Path(__file__).resolve().parents[1]/'results/2026-10-11-float-semantics/float-all.json.gz'
CLAIM = {'fadd32': {'daz1-ftz1', 'daz1-ftz2'}, 'fmul32': {'daz1-ftz2'}, 'fmadd32': {'daz1-ftz2-fused1'},
         'fadd32.sat': {'daz1-ftz1', 'daz1-ftz2'}, 'fmul32.sat': {'daz1-ftz2'}, 'fmadd32.sat': {'daz1-ftz2-fused1'},
         'fadd16': {'daz0-ftz0'}, 'fmul16': {'daz0-ftz0'}, 'fmadd16': {'daz0-ftz0-fused1'}}
NAN = {32: '0x7fc00000', 16: '0x7e00'}
st = json.loads(gzip.open(R).read())
fails = 0
for name, want in CLAIM.items():
    kind, w, asm, sat = F.OPS[name]
    raw = st['ops'][name]['raw']
    o = F.analyse(kind, w, sat, asm, [(tuple(x[:3]), x[3]) for x in raw])
    nan_ok = set(o['nan_outputs']) == {'0x0' if sat else NAN[w]}
    ok = set(o['matching_models']) == want and nan_ok and len(raw) >= 1300
    fails += not ok
    print(('ok   ' if ok else 'FAIL ')+f"{name}: {len(raw)} vectors, matching {sorted(o['matching_models'])}, NaN outputs {sorted(o['nan_outputs'])}")
print(f'{fails} failures'); sys.exit(1 if fails else 0)
