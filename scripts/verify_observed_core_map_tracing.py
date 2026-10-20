#!/usr/bin/env python3
"""Verify supplied-core prepared traces using retained maps and a lane-address oracle (host only)."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import verify_observed_core_map_replay as R

ROOT = R.ROOT
PACKAGE = ROOT / 'experiments/arithmetic/core-map-traces'
TARGET = Path('/scratch/apple-m2-playground/core-map-traces-target')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--result', type=Path)
    args = ap.parse_args()
    baseline_path = R.G.DATA / 'analysis.json'
    baseline = json.loads(baseline_path.read_text())
    jobs = []
    hashes = {}
    paths = sorted(R.G.DATA.glob('*.json.gz'))
    assert {p.name for p in paths} == set(baseline['records'])
    R.G.P.cov.install()
    for path in paths:
        assert R.sha(path) == baseline['records'][path.name]['sha256']
        r = json.load(gzip.open(path))
        b = r['gate']['base_gate']
        n, wg, c, a, sr = r['n'], r['wg'], b['chains'], b['adds'], b['selector']
        assert r['simulator_sha256'] == R.RECORDED_FUNCTIONAL_SHA256
        assert r['phase'] == 'finished' and not r.get('halted')
        code, _, _ = R.G.C.construct(n, c, a, sr)
        control, _, _ = R.G.C.construct(n, c, 0, 19)
        assert r['code'] == code.hex() and r['control_code'] == control.hex()
        R.V.independent_buffers(r['train'], n, c, a, wg, sr)
        for key in ('control_before', 'control_after'):
            assert r[key]['ok']
            R.V.independent_buffers(r[key], n, c, 0, wg, 19)
        hashes[path.name] = R.sha(path)
        if sr == 20:
            cores = r['train']['table_after'][n*c:-16:wg]
            assert len(cores) == n // wg
            jobs.append(dict(name=path.name, n=n, wg=wg, cores=cores))
    assert len(jobs) == 80
    env = dict(os.environ, CARGO_HOME='/scratch/rust/cargo', RUSTUP_HOME='/scratch/rust/rustup',
               CARGO_TARGET_DIR=str(TARGET))
    env['PATH'] = '/scratch/rust/cargo/bin:' + env['PATH']
    subprocess.run(['cargo', 'build', '--release', '--offline', '--manifest-path', str(PACKAGE/'Cargo.toml')],
                   env=env, check=True, timeout=180)
    binary = TARGET / 'release/observed-core-map-traces'
    sources = [Path(__file__), PACKAGE/'Cargo.toml', PACKAGE/'Cargo.lock', PACKAGE/'src/main.rs',
               ROOT.parent/'AGX-Performance-Simulator/rust/src/func.rs']
    source_hashes = {str(p.relative_to(ROOT.parent)): R.sha(p) for p in sources}
    binary_hash = R.sha(binary)
    run = subprocess.run([str(binary)], input=json.dumps(jobs), capture_output=True, text=True,
                         check=True, timeout=180)
    report = json.loads(run.stdout)
    assert [r['name'] for r in report['records']] == [j['name'] for j in jobs]
    for record, job in zip(report['records'], jobs):
        assert record['core_ids'] == len(set(job['cores']))
        assert record['workgroups'] == len(job['cores'])
        selected = record['requested_workgroups']
        assert selected[-1] == selected[0] and selected[:-1] == sorted(set(selected), reverse=True)
        assert {job['cores'][i] for i in selected} == set(job['cores'])
        assert record['simd_traces_checked'] == len(selected) * (job['wg']//32) * 6
        assert record['addresses_exact'] and record['caller_memory_unchanged']
    assert binary_hash == R.sha(binary)
    assert source_hashes == {str(p.relative_to(ROOT.parent)): R.sha(p) for p in sources}
    report.update(utc=datetime.now(timezone.utc).isoformat(), observed_maps_checked=len(jobs),
        raw_records_checked=len(paths), control_buffers_checked=len(paths)*2,
        geometry_analysis_sha256=R.sha(baseline_path), raw_record_sha256=hashes,
        verifier_sources=source_hashes, driver_sha256=binary_hash,
        core_map_input_sha256=hashlib.sha256(json.dumps(jobs).encode()).hexdigest(),
        total_simd_traces_checked=sum(r['simd_traces_checked'] for r in report['records']),
        supplied_state_not_timing_replay=True)
    if args.result:
        args.result.write_text(json.dumps(report, indent=1, sort_keys=True)+'\n')
    print(f"PASS {len(jobs)} observed maps, {report['total_simd_traces_checked']} independently checked SIMD traces; two memory snapshots, mapped/default/fresh paths; no hardware")


if __name__ == '__main__':
    main()
