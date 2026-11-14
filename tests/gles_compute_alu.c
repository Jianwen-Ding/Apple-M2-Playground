/* Render-path timing probe (surfaceless EGL, GLES 3.x through Mesa's open-source asahi driver).
 * Draws `layers` full-target quads (2 triangles each) into an offscreen WxH target and reports
 * wall time per frame (glFinish, no vendor tools).  Axes: target size, overdraw layers, fragment ALU
 * iterations, blend, MSAA samples, triangle count (small triangles).
 * usage: gles_raster W H layers alu blend samples tris_per_layer frames
 *   tris_per_layer 0 = one full-target quad per layer; N>0 = N small triangles tiling the target. */
#define _POSIX_C_SOURCE 200809L
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl32.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define EGL_FUNCS(X) \
 X(PFNEGLGETPLATFORMDISPLAYPROC, eglGetPlatformDisplay) X(PFNEGLINITIALIZEPROC, eglInitialize) \
 X(PFNEGLBINDAPIPROC, eglBindAPI) X(PFNEGLCHOOSECONFIGPROC, eglChooseConfig) \
 X(PFNEGLCREATECONTEXTPROC, eglCreateContext) X(PFNEGLMAKECURRENTPROC, eglMakeCurrent)
#define GL_FUNCS(X) \
 X(PFNGLCREATESHADERPROC, glCreateShader) X(PFNGLSHADERSOURCEPROC, glShaderSource) \
 X(PFNGLCOMPILESHADERPROC, glCompileShader) X(PFNGLGETSHADERIVPROC, glGetShaderiv) \
 X(PFNGLGETSHADERINFOLOGPROC, glGetShaderInfoLog) X(PFNGLCREATEPROGRAMPROC, glCreateProgram) \
 X(PFNGLATTACHSHADERPROC, glAttachShader) X(PFNGLLINKPROGRAMPROC, glLinkProgram) \
 X(PFNGLUSEPROGRAMPROC, glUseProgram) X(PFNGLGENBUFFERSPROC, glGenBuffers) \
 X(PFNGLBINDBUFFERPROC, glBindBuffer) X(PFNGLBUFFERDATAPROC, glBufferData) \
 X(PFNGLGENVERTEXARRAYSPROC, glGenVertexArrays) X(PFNGLBINDVERTEXARRAYPROC, glBindVertexArray) \
 X(PFNGLVERTEXATTRIBPOINTERPROC, glVertexAttribPointer) \
 X(PFNGLENABLEVERTEXATTRIBARRAYPROC, glEnableVertexAttribArray) \
 X(PFNGLGENFRAMEBUFFERSPROC, glGenFramebuffers) X(PFNGLBINDFRAMEBUFFERPROC, glBindFramebuffer) \
 X(PFNGLGENRENDERBUFFERSPROC, glGenRenderbuffers) X(PFNGLBINDRENDERBUFFERPROC, glBindRenderbuffer) \
 X(PFNGLRENDERBUFFERSTORAGEMULTISAMPLEPROC, glRenderbufferStorageMultisample) \
 X(PFNGLFRAMEBUFFERRENDERBUFFERPROC, glFramebufferRenderbuffer) \
 X(PFNGLCHECKFRAMEBUFFERSTATUSPROC, glCheckFramebufferStatus) \
 X(PFNGLVIEWPORTPROC, glViewport) X(PFNGLCLEARCOLORPROC, glClearColor) X(PFNGLCLEARPROC, glClear) \
 X(PFNGLDRAWARRAYSPROC, glDrawArrays) X(PFNGLENABLEPROC, glEnable) X(PFNGLDISABLEPROC, glDisable) \
 X(PFNGLBLENDFUNCPROC, glBlendFunc) X(PFNGLFINISHPROC, glFinish) \
 X(PFNGLGETUNIFORMLOCATIONPROC, glGetUniformLocation) X(PFNGLUNIFORM1FPROC, glUniform1f) \
 X(PFNGLREADPIXELSPROC, glReadPixels) X(PFNGLDISPATCHCOMPUTEPROC, glDispatchCompute) X(PFNGLBINDBUFFERBASEPROC, glBindBufferBase) X(PFNGLMAPBUFFERRANGEPROC, glMapBufferRange) X(PFNGLUNMAPBUFFERPROC, glUnmapBuffer) X(PFNGLMEMORYBARRIERPROC, glMemoryBarrier) X(PFNGLFLUSHPROC, glFlush) X(PFNGLINVALIDATEFRAMEBUFFERPROC, glInvalidateFramebuffer) X(PFNGLGETERRORPROC, glGetError)
#define DECL(t, n) static t p_##n;
EGL_FUNCS(DECL)
GL_FUNCS(DECL)
#define glCreateShader p_glCreateShader
#define glShaderSource p_glShaderSource
#define glCompileShader p_glCompileShader
#define glGetShaderiv p_glGetShaderiv
#define glGetShaderInfoLog p_glGetShaderInfoLog
#define glCreateProgram p_glCreateProgram
#define glAttachShader p_glAttachShader
#define glLinkProgram p_glLinkProgram
#define glUseProgram p_glUseProgram
#define glGenBuffers p_glGenBuffers
#define glBindBuffer p_glBindBuffer
#define glBufferData p_glBufferData
#define glGenVertexArrays p_glGenVertexArrays
#define glBindVertexArray p_glBindVertexArray
#define glVertexAttribPointer p_glVertexAttribPointer
#define glEnableVertexAttribArray p_glEnableVertexAttribArray
#define glGenFramebuffers p_glGenFramebuffers
#define glBindFramebuffer p_glBindFramebuffer
#define glGenRenderbuffers p_glGenRenderbuffers
#define glBindRenderbuffer p_glBindRenderbuffer
#define glRenderbufferStorageMultisample p_glRenderbufferStorageMultisample
#define glFramebufferRenderbuffer p_glFramebufferRenderbuffer
#define glCheckFramebufferStatus p_glCheckFramebufferStatus
#define glViewport p_glViewport
#define glClearColor p_glClearColor
#define glClear p_glClear
#define glDrawArrays p_glDrawArrays
#define glEnable p_glEnable
#define glDisable p_glDisable
#define glBlendFunc p_glBlendFunc
#define glFinish p_glFinish
#define glGetUniformLocation p_glGetUniformLocation
#define glUniform1f p_glUniform1f
#define glInvalidateFramebuffer p_glInvalidateFramebuffer
#define glGetError p_glGetError
#define glDispatchCompute p_glDispatchCompute
#define glBindBufferBase p_glBindBufferBase
#define glMapBufferRange p_glMapBufferRange
#define glUnmapBuffer p_glUnmapBuffer
#define glMemoryBarrier p_glMemoryBarrier
#define glReadPixels p_glReadPixels
#define glFlush p_glFlush

static void fail(const char *s) { fprintf(stderr, "FAIL %s\n", s); exit(1); }
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e3 + t.tv_nsec * 1e-6; }

static GLuint compile(GLenum type, const char *src) {
    GLuint s = glCreateShader(type); glShaderSource(s, 1, &src, NULL); glCompileShader(s);
    GLint ok; glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) { char log[2048]; glGetShaderInfoLog(s, sizeof log, NULL, log); fprintf(stderr, "%s\n", log); fail("compile"); }
    return s;
}


/* Compute counterpart of the fragment ALU-loop probe: usage gles_compute_alu W H alu frames [wg_x wg_y]; the shader runs the same
 * dependent chain per invocation (a=v.x+u, b=v.y; alu x { a=a*b+0.5; b=b*a-0.25 }) and stores one float per invocation. */
int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage\n"); return 2; }
    int W = atoi(argv[1]), H = atoi(argv[2]), alu = atoi(argv[3]), frames = atoi(argv[4]);
    int wx = argc > 5 ? atoi(argv[5]) : 32, wy = argc > 6 ? atoi(argv[6]) : 32;
    void *egl = dlopen("libEGL.so.1", RTLD_NOW); if (!egl) fail("libEGL");
    PFNEGLGETPROCADDRESSPROC gpa = (PFNEGLGETPROCADDRESSPROC)dlsym(egl, "eglGetProcAddress");
#define LOADE(t, n) p_##n = (t)gpa(#n);
#define LOADG(t, n) p_##n = (t)gpa(#n); if (!p_##n) fail("missing " #n);
    EGL_FUNCS(LOADE) GL_FUNCS(LOADG)
    EGLDisplay d = p_eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
    EGLint maj, min; if (!p_eglInitialize(d, &maj, &min)) fail("eglInitialize");
    p_eglBindAPI(EGL_OPENGL_ES_API);
    EGLint ca[] = {EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_SURFACE_TYPE, 0, EGL_NONE};
    EGLConfig cfg; EGLint n; if (!p_eglChooseConfig(d, ca, &cfg, 1, &n) || !n) fail("config");
    EGLint cx[] = {EGL_CONTEXT_MAJOR_VERSION, 3, EGL_CONTEXT_MINOR_VERSION, 1, EGL_NONE};
    EGLContext c = p_eglCreateContext(d, cfg, EGL_NO_CONTEXT, cx); if (!c) fail("context");
    if (!p_eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, c)) fail("makecurrent");
    char cs[16384]; const char *body = getenv("COMPUTE_FAMILY_A") ? "float c=a; for(int i=0;i<%d;i++){ c=c*c-0.25+b; } a=c;" : "for(int i=0;i<%d;i++){ a=a*b+0.5; b=b*a-0.25; }";
    char bd[8192]; if (getenv("COMPUTE_BODY")) snprintf(bd, sizeof bd, "float c=a+1.0,p=b+2.0,q=a*3.0,r=b*0.5,s=a-4.0,t=b+7.0; for(int i=0;i<%d;i++){ %s } a=a+b+c+p+q+r+s+t;", alu, getenv("COMPUTE_BODY")); else snprintf(bd, sizeof bd, body, alu);
    snprintf(cs, sizeof cs, "#version 310 es\nlayout(local_size_x=%d, local_size_y=%d) in;\nlayout(std430, binding=0) buffer B { float d[]; };\nuniform float u;\n"
        "void main(){ uvec2 id=gl_GlobalInvocationID.xy; float a=float(id.x)*(1.0/%d.0)+u, b=float(id.y)*(1.0/%d.0); %s if (a + b == 1234.5) d[id.y*uint(%d)+id.x]=a+b; }\n", wx, wy, W, H, bd, W);
    GLuint prog = glCreateProgram(); glAttachShader(prog, compile(GL_COMPUTE_SHADER, cs)); glLinkProgram(prog); glUseProgram(prog);
    glUniform1f(glGetUniformLocation(prog, "u"), 0.1f);
    GLuint buf; glGenBuffers(1, &buf); glBindBuffer(GL_SHADER_STORAGE_BUFFER, buf); glBufferData(GL_SHADER_STORAGE_BUFFER, (long)W * H * 4, NULL, GL_DYNAMIC_DRAW);
    glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, buf);
    double best = 1e30; 
    for (int r = 0; r < 6; r++) {
        double t0 = now();
        for (int f = 0; f < frames; f++) { glDispatchCompute(W / wx, H / wy, 1); glFlush(); }
        glFinish(); volatile float *p = (float *)glMapBufferRange(GL_SHADER_STORAGE_BUFFER, 0, 4, GL_MAP_READ_BIT); (void)*p; glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
        double dt = (now() - t0) / frames; if (r > 0 && dt < best) best = dt;
    }
    if (glGetError() != GL_NO_ERROR) fail("gl error");
    printf("{\"W\":%d,\"H\":%d,\"alu\":%d,\"wg\":[%d,%d],\"ms_best\":%.4f}\n", W, H, alu, wx, wy, best);
    return 0;
}
