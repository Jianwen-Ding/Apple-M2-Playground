import datetime, hashlib, json, os, pathlib, shutil, subprocess
root=pathlib.Path(__file__).resolve().parent
commands=[['uname','-a'],['ldconfig','-p'],['pkg-config','--list-all'],['rpm','-q','mesa-vulkan-drivers','mesa-dri-drivers','mesa-libEGL','vulkan-loader','vulkan-headers','spirv-tools','libdrm','mesa-libOpenCL','ocl-icd','mesa-libGLES'],['git','-C','/save/workspace/AGX_Probe/mesa','rev-parse','HEAD'],['git','-C','/save/workspace/AGX_Probe/applegpu','rev-parse','HEAD'],['rg','--files','--hidden','/scratch','-g','build.ninja','-g','meson-log.txt','-g','meson-info.json','-g','*asahi*.so','-g','*vulkan*.so','-g','*agx*.a'],['readelf','-Ws','/usr/lib64/libvulkan_asahi.so'],['ldd','/usr/lib64/libvulkan_asahi.so']]
r={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Inventory and capability enumeration only; no kernel submission','commands':[],'files':{},'tools':{}}
for name in ['cc','clang','meson','ninja','vulkaninfo','clinfo','eglinfo','glslangValidator','glslc','spirv-as','spirv-dis','xcrun']:
 r['tools'][name]=shutil.which(name)
for command in commands:
 entry={'argv':command,'timeout_seconds':10}
 try:
  p=subprocess.run(command,text=True,capture_output=True,timeout=10); entry.update(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
 except subprocess.TimeoutExpired as e: entry.update(timed_out=True,stdout=str(e.stdout),stderr=str(e.stderr))
 r['commands'].append(entry)
paths=['/usr/include/drm/asahi_drm.h','/usr/include/vulkan/vulkan.h','/usr/include/EGL/egl.h','/usr/include/GLES3/gl31.h','/usr/include/CL/cl.h','/usr/lib64/libvulkan_asahi.so','/usr/lib64/libvulkan.so.1','/usr/lib64/libEGL.so.1','/usr/lib64/libGLESv2.so.2','/usr/lib64/libOpenCL.so.1']
paths += [str(p) for d in ['/usr/share/vulkan/icd.d','/etc/OpenCL/vendors','/usr/share/glvnd/egl_vendor.d'] for p in pathlib.Path(d).glob('*')]
for name in paths:
 p=pathlib.Path(name); e={'exists':p.exists()}
 if p.exists():
  e.update(realpath=str(p.resolve()),size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
  if p.suffix=='.json': e['text']=p.read_text()
 r['files'][name]=e
(root/'inventory.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'utc':r['utc'],'tools':r['tools'],'files':{k:v['exists'] for k,v in r['files'].items()},'commands':[{k:v for k,v in e.items() if k not in ['stdout','stderr']} for e in r['commands']]},indent=2))
