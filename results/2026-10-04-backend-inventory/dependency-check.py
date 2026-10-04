import ctypes, datetime, hashlib, importlib, json, pathlib, sys
sys.dont_write_bytecode=True
root=pathlib.Path(__file__).resolve().parent
r={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Dynamic loading and offline Python import only; no GPU API calls','libraries':{},'imports':{},'hashes':{}}
for name in ['libvulkan.so.1','libvulkan_asahi.so','libEGL.so.1','libEGL_mesa.so.0','libgallium-25.1.9.so','libGLESv2.so.2','libOpenCL.so.1','libdisplay-info.so.2']:
 try:ctypes.CDLL(name);r['libraries'][name]='load success'
 except OSError as e:r['libraries'][name]=str(e)
sys.path.insert(0,'/save/workspace/AGX_Probe/applegpu')
for name in ['fma','srgb','applegpu','disassemble','assemble']:
 try:importlib.import_module(name);r['imports'][name]='import success'
 except Exception as e:r['imports'][name]=repr(e)
for p in list(root.glob('*.py'))+list(root.glob('*.c'))+[pathlib.Path('/save/workspace/AGX_Probe/mesa/include/vulkan/vulkan_core.h')]:
 r['hashes'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
(root/'dependency-check.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
