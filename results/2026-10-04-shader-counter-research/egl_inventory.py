"""Bounded context/capability inventory only: no shaders, draws or dispatches."""
import ctypes as C
import json
import os
import time

e = C.CDLL('libEGL.so.1')
P, I, U = C.c_void_p, C.c_int, C.c_uint
def egl(name, result, args):
    f = getattr(e, name); f.restype = result; f.argtypes = args
    return f
gp = egl('eglGetProcAddress', P, [C.c_char_p])
def proc(name, result, args):
    ptr = gp(name.encode())
    if not ptr:
        raise RuntimeError('missing procedure '+name)
    return C.CFUNCTYPE(result, *args)(ptr)
err = egl('eglGetError', U, [])
def check(ok, label):
    if not ok:
        raise RuntimeError(f'{label}: EGL error {err():#x}')
qs = egl('eglQueryString', C.c_char_p, [P, I])
out = {'scope':'context creation and capability queries; no shaders/draws/dispatch',
       'environment':{k:v for k,v in os.environ.items() if k.startswith(('EGL','MESA','LIBGL','GALLIUM'))}}
out['client_extensions'] = (qs(None, 0x3055) or b'').decode()
getdisplay = proc('eglGetPlatformDisplayEXT', P, [U,P,C.POINTER(I)])
d = getdisplay(0x31DD, None, (I*1)(0x3038)) # Mesa surfaceless
check(d, 'platform display')
initialize = egl('eglInitialize', U, [P,C.POINTER(I),C.POINTER(I)])
major, minor = I(), I(); check(initialize(d,C.byref(major),C.byref(minor)), 'initialize')
out['egl_version'] = [major.value,minor.value]
out['egl_vendor'] = (qs(d,0x3053) or b'').decode()
out['egl_extensions'] = (qs(d,0x3055) or b'').decode()
check(egl('eglBindAPI',U,[U])(0x30A0),'bind GLES')
choose = egl('eglChooseConfig',U,[P,C.POINTER(I),C.POINTER(P),I,C.POINTER(I)])
cfg, count = P(), I()
attrs = (I*7)(0x3040,0x40,0x3033,1,0x3024,8,0x3038)
check(choose(d,attrs,C.byref(cfg),1,C.byref(count)) and count.value,'choose GLES3 config')
ctx = egl('eglCreateContext',P,[P,P,P,C.POINTER(I)])(d,cfg,None,(I*3)(0x3098,3,0x3038))
check(ctx,'create context')
make = egl('eglMakeCurrent',U,[P,P,P,P]); check(make(d,None,None,ctx),'make current')
gs = proc('glGetString',C.c_char_p,[U])
gi = proc('glGetIntegerv',None,[U,C.POINTER(I)])
gsi = proc('glGetStringi',C.c_char_p,[U,U])
ge = proc('glGetError',U,[])
out['gl'] = {name:(gs(token) or b'').decode() for name,token in [('vendor',0x1F00),('renderer',0x1F01),('version',0x1F02),('shading_language',0x8B8C)]}
n=I(); gi(0x821D,C.byref(n)); assert 0<=n.value<=4096
out['gl_extensions'] = sorted(gsi(0x1F03,j).decode() for j in range(n.value))
out['gl_initial_error'] = ge()
if 'GL_EXT_disjoint_timer_query' in out['gl_extensions']:
    gq=proc('glGetQueryivEXT',None,[U,U,C.POINTER(I)])
    out['counter_bits']={}
    for name,token in [('elapsed',0x88BF),('timestamp',0x8E28)]:
        bits=I(); gq(token,0x8864,C.byref(bits)); out['counter_bits'][name]={'bits':bits.value,'error':ge()}
    disjoint=I(); gi(0x8FBB,C.byref(disjoint)); out['disjoint']={'value':disjoint.value,'error':ge()}
    # This synchronous state getter does not create a query or submit a shader.
    get64=proc('glGetInteger64v',None,[U,C.POINTER(C.c_int64)])
    out['server_timestamp_samples']=[]
    for j in range(3):
        v=C.c_int64(); before=time.monotonic_ns(); get64(0x8E28,C.byref(v)); after=time.monotonic_ns()
        out['server_timestamp_samples'].append({'value':v.value,'before':before,'after':after,'error':ge()})
        if j<2: time.sleep(0.01)
    out['procedure_addresses_present']={name:bool(gp(name.encode())) for name in ['glBeginQueryEXT','glEndQueryEXT','glQueryCounterEXT','glGetQueryObjectui64vEXT','glGetQueryObjectuivEXT','glDispatchCompute','glFenceSync','glClientWaitSync']}
check(make(d,None,None,None),'unbind')
check(egl('eglDestroyContext',U,[P,P])(d,ctx),'destroy context')
check(egl('eglTerminate',U,[P])(d),'terminate')
print(json.dumps(out,indent=2))
