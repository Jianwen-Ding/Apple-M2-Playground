#!/usr/bin/env python3
"""Hardware regression for novel-results/2026-10-11-tg-memory-addressing.

Reruns scripts/run_drm_tg_layout.py (only decoded, Mesa-emitted instruction forms) and applies
the same checks as scripts/verify_tg_addressing.py to the fresh result.
Default (no --hardware): checks the retained evidence only.
"""
import subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main():
    if '--hardware' not in sys.argv:
        return subprocess.run([sys.executable, '-B', str(REPO/'scripts/verify_tg_addressing.py')]).returncode
    d = Path(tempfile.mkdtemp(prefix='tgaddr-', dir='/scratch/apple-m2-playground/drm-compute'))
    r = subprocess.run([sys.executable, '-B', 'run_drm_tg_layout.py', '--output', str(d/'layout.json')], cwd=REPO/'scripts',
                       capture_output=True, text=True, timeout=600)
    if r.returncode: sys.exit(r.stdout[-400:]+r.stderr[-400:])
    return subprocess.run([sys.executable, '-B', str(REPO/'scripts/verify_tg_addressing.py'), str(d)]).returncode


if __name__ == '__main__':
    sys.exit(main())
