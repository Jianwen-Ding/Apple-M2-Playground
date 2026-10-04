import datetime,json,os,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parent
compile=['cc','-std=c11','-Wall','-Wextra','-Werror','-O2','-I/save/workspace/AGX_Probe/mesa/include',str(root/'vulkan-capabilities.c'),'-ldl','-o',str(root/'vulkan-capabilities')]
env=os.environ.copy()
for key in list(env):
 if key.startswith(('VK_','MESA_','ASAHI_','AGX_','HK_')) or key in ['LD_PRELOAD','LD_LIBRARY_PATH']:env.pop(key)
env.update(VK_DRIVER_FILES='/usr/share/vulkan/icd.d/asahi_icd.aarch64.json',VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/asahi_icd.aarch64.json',VK_LOADER_LAYERS_DISABLE='~implicit~')
records=[]
for argv in [compile,[str(root/'vulkan-capabilities')]]:
 e={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'timeout_seconds':15,'env_overrides':{k:env[k] for k in ['VK_DRIVER_FILES','VK_ICD_FILENAMES','VK_LOADER_LAYERS_DISABLE']}}
 try:
  p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=15);e.update(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
 except subprocess.TimeoutExpired as x:e.update(timed_out=True,stdout=(x.stdout or b'').decode(),stderr=(x.stderr or b'').decode())
 records.append(e)
 if e.get('returncode')!=0:break
(root/'vulkan-capabilities.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(records,indent=2))
