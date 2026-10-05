#!/usr/bin/env python3
"""Recompute the retained SR lane/context observations; no GPU or vendor imports."""
import hashlib
import json
from pathlib import Path
import struct
import sys

import verify_sr_evidence as evidence

ROOT=Path(__file__).resolve().parents[1]/'results/2026-10-04-sr-scan'


def require(ok,message):
    if not ok:raise ValueError(message)


def load(name):return json.loads((ROOT/(name+'.json')).read_text())


def main():
    words=0;samples=0;ticking=set()
    try:
        for path in sorted(ROOT.glob('*.json')):
            if path.name in ('manifest-sha256.json','packaging-index.json','verification.json'):continue
            record=json.loads(path.read_text())
            if path.name.startswith('failed-'):
                require(record['passed'] is False and record.get('error'), 'failed-run classification')
                continue
            if not path.name.startswith('context-'):
                deltas=evidence.verify(record,partial=not path.name.startswith('full-'))
                ticking.update(sr for sr,values in deltas.items() if any(values))
                for observation in record['observations']:
                    for sample in observation['samples']:
                        samples+=1;words+=len(bytes.fromhex(sample['readback_hex']))//4
                for sample in record['controls']:
                    samples+=1;words+=len(bytes.fromhex(sample['readback_hex']))//4
        # Independent mathematical descriptions for prefix masks and sparse masks.
        for name in [f'count-{n}' for n in (1,2,3,4,5,7,16,17,31,32,33,63,64,65,257)]+['sparse-even']:
            record=load(name);n=record['count'];sparse=record.get('even_mask',False)
            for observation in record['observations']:
                sr=observation['selector']
                if sr not in (16,56,57,58,59,60):continue
                for sample in observation['samples']:
                    expected=[]
                    for i in range(n):
                        if sparse and i%2:expected.append(0xcdcdcdcd);continue
                        if sr==16:value=i%4
                        elif sr==56:value=(i%4)//2 if sparse else i%4
                        elif sr==58:value=(i%32)//2 if sparse else i%32
                        elif sr in (57,59):
                            width=4 if sr==57 else 32
                            start=i//width*width
                            value=sum(not sparse or j%2==0 for j in range(start,min(start+width,n)))
                        else:value=15
                        expected.append(value)
                    require(sample['values']==expected,f'{name} SR{sr} behavior mismatch')
        base=load('full-single')
        for n in (1,33,65,257):
            record=load(f'context-{n}')
            require(record['passed'] and record['count']==n and record['repeats']==12,'context dimensions')
            require(record['cases'][0]['name']=='control-before' and record['cases'][-1]['name']=='control-after','context controls')
            for case in record['cases']:
                blob=bytes.fromhex(base['control_hex']) if case['selector'] is None else evidence.derived_blob(base,case['patch'])
                require(case['shader_sha256']==hashlib.sha256(blob).hexdigest(),'context shader hash')
                events=case['events']
                require(all(e.get('result')==0 for e in events if 'api' in e),'context API failure')
                for api,count in [('vkCreateShadersEXT',1),('vkQueueSubmit',12),('vkWaitForFences',12)]:
                    require(sum(e.get('api')==api for e in events)==count,'context API counts')
                expected_completions=[{'completed':True,'dispatch':True,'count':n,'words':(n+31)//32*32+32}]*12
                require([e for e in events if e.get('completed') is True]==expected_completions,'context completion markers')
                require(len(case['samples'])==12,'context sample count')
                for ordinal,sample in enumerate(case['samples']):
                    require(sample['iteration']==ordinal,'context iteration')
                    raw=bytes.fromhex(sample['readback_hex']);rounded=(n+31)//32*32
                    require(hashlib.sha256(raw).hexdigest()==sample['readback_sha256'],'context readback hash')
                    require(len(raw)==(rounded+32)*4,'context readback size')
                    actual=list(struct.unpack('<'+'I'*(rounded+32),raw))
                    initial=[0xcdcdcdcd]*(rounded+16)+[0xa5a50000+i for i in range(16)]
                    require(actual[:8]==initial[:8] and actual[8+n:]==initial[8+n:],'context guards')
                    require(actual[8:8+n]==sample['values'],'context raw values')
                    if case['selector'] is None:require(sample['values']==[0x12345678]*n,'context control')
                    samples+=1;words+=len(actual)
                if case['selector']==21:require(all(s['values']==case['samples'][0]['values'] for s in case['samples']),'SR21 context stability')
                if case['selector']==32:
                    vectors=[s['values'] for s in case['samples']]
                    require(all(len(set(v))==1 for v in vectors),'SR32 lane uniformity')
                    require(all((vectors[j][0]-vectors[j+1][0])&0xffffffff==0x24000 for j in range(11)),'SR32 command step')
        require(not ticking,'paired reads progressed: '+str(sorted(ticking)))
        result={'passed':True,'verified_readbacks':samples,'verified_uint32_words':words,
                'paired_read_ticking_selectors':sorted(ticking), 'sr32_command_step_hex':'0x24000'}
        print(json.dumps(result));return 0
    except (OSError,ValueError,KeyError,TypeError) as e:
        print(json.dumps({'passed':False,'error':str(e)}));return 1


if __name__=='__main__':sys.exit(main())
