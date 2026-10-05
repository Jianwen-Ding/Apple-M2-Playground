#!/usr/bin/env python3
"""Repeat selected SR reads at active-lane boundaries; serial GPU work only."""
import datetime
import json
from pathlib import Path
import subprocess
import sys

COUNTS = (1,2,3,4,5,7,16,17,31,32,33,63,64,65,257)
SELECTORS = '7,15,16,19,20,21,24,25,32,56,57,58,59,60,97,113,114'


def main():
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=Path('/scratch/apple-m2-playground/sr-characterization')/stamp
    out.mkdir(parents=True,exist_ok=False)
    record={'passed':False,'counts':list(COUNTS),'selectors':SELECTORS,'runs':[]}
    try:
        for count in COUNTS:
            child=out/f'count-{count}'
            result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('run_agx_sr_scan.py')),
                '--selectors',SELECTORS,'--count',str(count),'--repeats','2','--output',str(child)],
                capture_output=True,timeout=180)
            (out/f'count-{count}.stdout').write_bytes(result.stdout)
            (out/f'count-{count}.stderr').write_bytes(result.stderr)
            record['runs'].append({'count':count,'output':str(child),'returncode':result.returncode})
            (out/'record.json').write_text(json.dumps(record,indent=2)+'\n')
            if result.returncode!=0: raise RuntimeError(f'count {count} failed')
            print(json.dumps({'count':count,'passed':True}),flush=True)
        record['passed']=True
    except Exception as e:
        record['error']=str(e)
    finally:
        (out/'record.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps({'passed':record['passed'],'output':str(out)}),flush=True)
    return 0 if record['passed'] else 1


if __name__=='__main__':
    main()
