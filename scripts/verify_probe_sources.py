"""Resolve recorded builder hashes across the measured-model integration.

The original probes rejected unmodelled actual programs. Once hardware evidence
supports a simulator change, current builders gate complete programs instead.
Keep the original source bytes so old diagnostics remain attributable rather
than rewriting history or requiring an obsolete simulator to check hardware.
"""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ARCHIVES=(ROOT/'results/2026-10-20-control-simulator/source-before-model',
          ROOT/'results/2026-10-20-call-r1/source-before-model',
          ROOT/'results/2026-10-20-ret-prepop/source-before-model',
          ROOT/'results/2026-10-20-stopped-r0/source-before-model',
          ROOT/'results/2026-10-20-ret-stale-exec/source-before-model')


def require_source(path,recorded_sha):
    path=Path(path)
    candidates=[path]
    for archive in ARCHIVES:
        candidates.append(archive/(path.name+'.txt'))
        candidates.extend(archive.glob('*--'+path.name+'.txt'))
    assert any(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==recorded_sha for p in candidates), \
        'recorded probe source unavailable or changed: '+path.name
