import ctypes as c, json, pathlib
r={'scope':'Surfaceless EGL capability/context query; no shader creation or dispatch','calls':{}}
lib=c.CDLL('libEGL.so.1')
def fn(name,ret,args):
 f=getattr(lib,name);f.restype=ret;f.argtypes=args;return f
get=fn('eglGetProcAddress',c.c_void_p,[c.c_char_p]);err=fn('eglGetError',c.c_uint,[])
query=fn('eglQueryString',c.c_char_p,[c.c_void_p,c.c_int])
init=fn('eglInitialize',c.c_uint,[c.c_void_p,c.POINTER(c.c_int),c.POINTER(c.c_int)])
platform=fn('eglGetPlatformDisplay',c.c_void_p,[c.c_uint,c.c_void_p,c.POINTER(c.c_ssize_t)])
display=platform(0x31DD,None,None);r['calls']['eglGetPlatformDisplay']={'ok':bool(display),'error':hex(err())}
a,b=c.c_int(),c.c_int();ok=init(display,c.byref(a),c.byref(b));r['calls']['eglInitialize']={'ok':bool(ok),'error':hex(err()),'version':[a.value,b.value]}
context=None
if ok:
 qda=get(b'eglQueryDisplayAttribEXT');qds=get(b'eglQueryDeviceStringEXT')
 if qda and qds:
  device=c.c_ssize_t()
  v=c.CFUNCTYPE(c.c_uint,c.c_void_p,c.c_int,c.POINTER(c.c_ssize_t))(qda)(display,0x322C,c.byref(device))
  r['calls']['eglQueryDisplayAttribEXT_device']={'ok':bool(v),'error':hex(err())}
  if v:
   dq=c.CFUNCTYPE(c.c_char_p,c.c_void_p,c.c_int)(qds)
   for label,n in [('device_extensions',0x3055),('drm_device_file',0x3233),('drm_render_node_file',0x3377)]:
    val=dq(device.value,n);r[label]=val.decode() if val else None
 for label,n in [('vendor',0x3053),('version',0x3054),('extensions',0x3055),('client_apis',0x308D)]:
  v=query(display,n);r[label]=v.decode() if v else None
 bind=fn('eglBindAPI',c.c_uint,[c.c_uint]);r['calls']['eglBindAPI_ES']=bool(bind(0x30A0))
 choose=fn('eglChooseConfig',c.c_uint,[c.c_void_p,c.POINTER(c.c_int),c.POINTER(c.c_void_p),c.c_int,c.POINTER(c.c_int)])
 attrs=(c.c_int*7)(0x3040,0x0040,0x3033,0x0001,0x3024,8,0x3038)
 config=c.c_void_p();count=c.c_int();v=choose(display,attrs,c.byref(config),1,c.byref(count));r['calls']['eglChooseConfig_ES3']={'ok':bool(v),'count':count.value,'error':hex(err())}
 if v and count.value:
  create=fn('eglCreateContext',c.c_void_p,[c.c_void_p,c.c_void_p,c.c_void_p,c.POINTER(c.c_int)])
  attrs=(c.c_int*5)(0x3098,3,0x30FB,1,0x3038);context=create(display,config,None,attrs)
  r['calls']['eglCreateContext_ES31']={'ok':bool(context),'error':hex(err())}
  if context:
   current=fn('eglMakeCurrent',c.c_uint,[c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p]);v=current(display,None,None,context)
   r['calls']['eglMakeCurrent_surfaceless']={'ok':bool(v),'error':hex(err())}
   if v:
    gs=c.CFUNCTYPE(c.c_char_p,c.c_uint)(get(b'glGetString'))
    for label,n in [('gl_vendor',0x1F00),('gl_renderer',0x1F01),('gl_version',0x1F02),('glsl_version',0x8B8C)]:
     val=gs(n);r[label]=val.decode() if val else None
    gi=c.CFUNCTYPE(None,c.c_uint,c.POINTER(c.c_int))(get(b'glGetIntegerv'))
    r['limits']={}
    for label,n in [('max_compute_work_group_invocations',0x90EB),('max_shader_storage_buffer_bindings',0x90DD)]:
     val=c.c_int();gi(n,c.byref(val));r['limits'][label]=val.value
    r['compute_function_addresses']={name:bool(get(name.encode())) for name in ['glDispatchCompute','glBindBufferBase','glMemoryBarrier','glFenceSync','glClientWaitSync','glMapBufferRange']}
   current(display,None,None,None)
   fn('eglDestroyContext',c.c_uint,[c.c_void_p,c.c_void_p])(display,context)
 fn('eglTerminate',c.c_uint,[c.c_void_p])(display)
print(json.dumps(r,indent=2))
