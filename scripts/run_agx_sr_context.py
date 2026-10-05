#!/usr/bin/env python3
"""Separate context-allocation changes from values progressing within one context."""
import datetime
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from patch_agx_sr import patch
from run_agx_sr_scan import inspect_buffer
from run_vulkan_compute import DRIVER, DRIVER_HASH, ICD

REPO=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count',type=int,default=257)
    parser.add_argument('--selectors',default='21,113,20,16,57,59,15,19,24,25,32,97,114')
    args=parser.parse_args()
    selectors=[int(s) for s in args.selectors.split(',')]
    if not 1<=args.count<=257 or len(set(selectors))!=len(selectors) or any(not 0<=s<=255 for s in selectors):
        parser.error('bounded count and unique selectors required')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=Path('/scratch/apple-m2-playground/sr-context-runs')/stamp
    out.mkdir(parents=True,exist_ok=False)
    record={'passed':False,'count':args.count,'repeats':12,'spacing_ms':10,'cases':[]}
    env={k:v for k,v in os.environ.items() if not k.startswith(('VK_','MESA_','ASAHI_','AGX_','HK_','LIBGL_','GALLIUM_','DRI_','LD_'))}
    env.update(VK_DRIVER_FILES=str(ICD),VK_ICD_FILENAMES=str(ICD),VK_LOADER_LAYERS_DISABLE='~implicit~',
               LD_LIBRARY_PATH='/scratch/apple-m2-playground/vulkan-runtime/usr/lib64',MESA_SHADER_CACHE_DISABLE='true')
    def execute(argv,name,timeout):
        result=subprocess.run(list(map(str,argv)),env=env,capture_output=True,timeout=timeout)
        (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
        if result.returncode: raise RuntimeError(name+' failed')
        return result.stdout
    try:
        if sha(DRIVER)!=DRIVER_HASH:raise ValueError('driver changed')
        record['driver_sha256']=sha(DRIVER)
        source=REPO/'tests/vulkan_sr_repeated.c'
        shutil.copy2(source,out/source.name)
        shutil.copy2(__file__,out/Path(__file__).name)
        record['source_hashes']={str(source):sha(source),str(Path(__file__)):sha(__file__)}
        binary=out/'vulkan_sr_repeated'
        execute(['cc','-std=c11','-Wall','-Wextra','-Werror','-O2','-I/save/workspace/AGX_Probe/mesa/include',source,'-ldl','-o',binary],'build',30)
        record['executable_sha256']=sha(binary)
        blob=bytes.fromhex(json.loads((REPO/'novel-results/2026-10-04-first-agx-instruction/patch.json').read_text())['input_hex'])
        def case(selector,name):
            shader,evidence=(blob,None) if selector is None else patch(blob,selector)
            code=out/(name+'.bin');code.write_bytes(shader)
            stdout=execute([binary,'import',code,args.count,'/dev/dri/renderD128',out/name,out/'unused',12],name,20)
            events=[json.loads(s) for s in stdout.decode().splitlines()]
            for api,n in [('vkCreateShadersEXT',1),('vkQueueSubmit',12),('vkWaitForFences',12)]:
                matching=[e for e in events if e.get('api')==api]
                if len(matching)!=n or any(e.get('result')!=0 for e in matching):raise ValueError('API events: '+api)
            completions=[e for e in events if e.get('completed') is True]
            if len(completions)!=12 or any(e.get('count')!=args.count or e.get('words')!=(args.count+31)//32*32+32 for e in completions):raise ValueError('missing completions')
            samples=[]
            for i in range(12):
                path=out/(name+f'.{i}.readback');data=path.read_bytes()
                values=inspect_buffer(data,args.count,(lambda j:0x12345678) if selector is None else None)
                samples.append({'iteration':i,'values':values,'readback_hex':data.hex(),'readback_sha256':sha(path)})
            record['cases'].append({'selector':selector,'name':name,'patch':evidence,'shader_sha256':sha(code),'events':events,'samples':samples,
                                    'all_dispatches_equal':all(s['values']==samples[0]['values'] for s in samples)})
            if sha(DRIVER)!=DRIVER_HASH:raise ValueError('driver changed during run')
            (out/'record.json').write_text(json.dumps(record,indent=2)+'\n')
        case(None,'control-before')
        for selector in selectors:case(selector,f'sr{selector:03d}')
        case(None,'control-after')
        record['passed']=True
    except Exception as e:record['error']=str(e)
    finally:
        (out/'record.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps({'passed':record['passed'],'output':str(out),'error':record.get('error')}),flush=True)
    return 0 if record['passed'] else 1


if __name__=='__main__':main_status=main();sys.exit(main_status)
