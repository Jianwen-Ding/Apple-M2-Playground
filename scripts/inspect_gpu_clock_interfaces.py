#!/usr/bin/env python3
"""Read-only inventory of clock/PM interfaces exposed to this container; no DRM ioctls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    roots=['/sys/class/devfreq','/sys/kernel/debug/dri','/sys/kernel/debug/asahi','/sys/module/asahi/parameters']
    entries={}
    for name in roots:
        path=Path(name)
        try:
            entries[name]=dict(exists=path.exists(),children=sorted(p.name for p in path.iterdir()) if path.is_dir() else [])
        except OSError as e:entries[name]=dict(error=str(e))
    device=Path('/sys/class/drm/renderD128/device')
    report=dict(utc=datetime.now(timezone.utc).isoformat(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        interfaces=entries,render_device_target=str(device.resolve()),hardware_submissions=0,drm_ioctls=0)
    try:report['gpu_device_files']=sorted(p.name for p in device.iterdir())
    except OSError as e:report['gpu_device_error']=str(e)
    report['runtime_pm']={}
    for key in ('control','runtime_status','runtime_active_time','runtime_suspended_time','autosuspend_delay_ms'):
        try:report['runtime_pm'][key]=(device/'power'/key).read_text().strip()
        except OSError as e:report['runtime_pm'][key]=dict(error=str(e))
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print(json.dumps(report,indent=1,sort_keys=True))


if __name__=='__main__':main()
