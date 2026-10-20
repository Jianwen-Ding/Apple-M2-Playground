#!/usr/bin/env python3
"""Replay original hardware shader/input bytes through the measured call/ret model.

No shader regeneration and no GPU access. Exact complete main/table buffers
are compared for every case, including inactive writes and untouched tails.
"""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path

import probe_empty_stop as E

ROOT=E.ROOT
GROUPS={'2026-10-20-ret-winner':64,'2026-10-20-call-winner':74,'2026-10-20-sparse-control':248,'2026-10-20-call-r1':22,'2026-10-20-three-targets':72,'2026-10-20-empty-stop':17,'2026-10-20-ret-prepop':36,'2026-10-20-ret-levels':21,'2026-10-20-empty-ret-state':16,'2026-10-20-masked-r0':24,'2026-10-20-stopped-r0':9,'2026-10-20-stopped-shuffle-index':256,'2026-10-20-dead-index-or':256,'2026-10-20-stopped-native-shuffle':160,'2026-10-20-native-dead-index-or':320,'2026-10-20-nested-divergent':12,'2026-10-20-nested-early-return':24,'2026-10-20-nested-partial-outer':144,'2026-10-20-call-mask-reserve':192,'2026-10-20-deep-call-reserve':192,'2026-10-20-deep-ret-counters':16}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',type=Path)
    args=parser.parse_args()
    summary=dict(utc=datetime.now(timezone.utc).isoformat(),groups={},cases=0,passed=False,
                 simulator_binary_sha256=sha(E.P.cov.RUN),
                 simulator_func_sha256=sha(ROOT.parent/'AGX-Performance-Simulator/rust/src/func.rs'),
                 simulator_sources={name:sha(ROOT.parent/'AGX-Performance-Simulator'/name) for name in
                                    ('rust/src/func.rs','rust/src/isa/exec.rs','rust/src/isa/compiled.rs','rust/src/isa/mod.rs')},
                 records={})
    E.P.cov.install()
    with E.measured_model():
        for group,count in GROUPS.items():
            paths=sorted((ROOT/'results'/group).glob('*.json.gz'))
            assert len(paths)==count,'missing/extra corpus records: '+group
            for path in paths:
                r=json.load(gzip.open(path))
                assert r['variant']['ok'] and r['recovery_control_passed'] and not r.get('halted')
                assert r['n']==r['wg']==32 and r['regs']==64
                code=bytes.fromhex(r['code'])
                assert code[-2:]==bytes.fromhex('8800')
                out,table=E.P.cov.simulate(code,r['n'],r['wg'],r['regs'],0,r['table_in'])
                assert (out,table)==(r['variant']['out'],r['variant']['table_after']),str(path)
                summary['records'][str(path.relative_to(ROOT))]=sha(path)
            summary['groups'][group]=count;summary['cases']+=count
            print('PASS original shader/input/readback replay:',group,count)
    assert summary['cases']==sum(GROUPS.values())
    assert summary['simulator_binary_sha256']==sha(E.P.cov.RUN), 'simulator changed during replay'
    summary['passed']=True
    if args.result:
        args.result.write_text(json.dumps(summary,indent=1,sort_keys=True)+'\n')
    print(f'PASS {summary["cases"]} exact hardware cases; model opt-in required, no GPU used')


if __name__=='__main__':main()
