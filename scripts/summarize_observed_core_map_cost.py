#!/usr/bin/env python3
"""Compare exhaustive supplied-map estimates to retained scalar-peak estimates; no hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    current_path=ROOT/'results/2026-10-20-observed-core-map-cost/analysis.json'
    old_path=ROOT/'results/2026-10-20-integer-geometry-cost/analysis.json'
    current=json.loads(current_path.read_text());old=json.loads(old_path.read_text())
    assert current['phase']=='finished' and sha(old_path)==current['geometry_analysis_sha256']
    assert old['dispatch_binary_sha256']==current['archived_model_sha256']
    entries={}
    for name, entry in current['records'].items():
        if 'prediction' not in entry or '-k64-' not in name:continue
        m=re.fullmatch(r'integer-core-s20-n(\d+)-w(\d+)-c(\d+)-a(\d+)-k64-t(\d+)\.json\.gz',name)
        n,wg,c,a,_=map(int,m.groups())
        pred=entry['prediction'];hist={str(core['id']):len(core['workgroups']) for core in pred['cores']}
        candidates=[t for t in old['placement_sensitivity'][f'{n}:{wg}:{c}:{a}:20']
                    if t['last_dispatch_ns']==entry['last_dispatch_ns'] and t['core_map']['workgroups_per_core']==hist]
        assert candidates and all(t['model_with_observed_peak']==candidates[0]['model_with_observed_peak'] for t in candidates)
        peak=candidates[0]['model_with_observed_peak'];ratio=pred['time_us']/peak['time_us']
        entries[name]=dict(supplied_map_us=pred['time_us'],observed_peak_model_us=peak['time_us'],
            supplied_to_peak_ratio=ratio,hardware_last_ns=entry['last_dispatch_ns'],
            last_to_supplied_ratio=entry['last_dispatch_model_ratio'],
            last_to_peak_ratio=candidates[0]['last_dispatch_to_peak_model_ratio'])
    assert len(entries)==72
    fixed=[e for name,e in entries.items() if '-n131072-' in name]
    assert len(fixed)==48
    metrics=lambda key:dict(minimum=min(e[key] for e in fixed),maximum=max(e[key] for e in fixed),median=statistics.median(e[key] for e in fixed))
    report=dict(cost_analysis_sha256=sha(current_path),geometry_analysis_sha256=sha(old_path),
        summarizer_sha256=sha(Path(__file__)),records=entries,full_maps_compared=72,fixed_grid_maps=48,
        fixed_grid_supplied_to_peak=metrics('supplied_to_peak_ratio'),
        fixed_grid_last_to_supplied=metrics('last_to_supplied_ratio'),fixed_grid_last_to_peak=metrics('last_to_peak_ratio'),
        calibration_changed=False,hardware_submissions=0)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    for key in ('fixed_grid_supplied_to_peak','fixed_grid_last_to_supplied','fixed_grid_last_to_peak'):print(key,report[key])


if __name__=='__main__':main()
