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
 X(PFNGLREADPIXELSPROC, glReadPixels) X(PFNGLFLUSHPROC, glFlush) X(PFNGLINVALIDATEFRAMEBUFFERPROC, glInvalidateFramebuffer) X(PFNGLGETERRORPROC, glGetError)
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

int main(int argc, char **argv) {
    if (argc < 9) { fprintf(stderr, "usage: %s W H layers alu blend samples tris frames\n", argv[0]); return 2; }
    int W = atoi(argv[1]), H = atoi(argv[2]), layers = atoi(argv[3]), alu = atoi(argv[4]);
    int blend = atoi(argv[5]), samples = atoi(argv[6]), tris = atoi(argv[7]), frames = atoi(argv[8]);
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
    EGLint cx[] = {EGL_CONTEXT_MAJOR_VERSION, 3, EGL_CONTEXT_MINOR_VERSION, 0, EGL_NONE};
    EGLContext c = p_eglCreateContext(d, cfg, EGL_NO_CONTEXT, cx); if (!c) fail("context");
    if (!p_eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, c)) fail("makecurrent");

    /* RASTER_VARY=N: N vec4 varyings summed by the fragment shader (RASTER_FLAT=1: flat -> ldcf instead of iterproj) */
    int nv = getenv("RASTER_VARY") ? atoi(getenv("RASTER_VARY")) : 0; const char *fq = getenv("RASTER_FLAT") ? "flat " : "";
    char fs[8192], vs[8192]; int o = 0, q = 0;
    if (nv > 0) {
        o += snprintf(fs + o, sizeof fs - o, "#version 300 es\nprecision highp float;\nuniform float u;\n%sin vec4 v[%d];\nout vec4 o;\n"
                      "void main(){ vec4 a=vec4(u); for(int i=0;i<%d;i++){ a=a*0.999+v[i]; } float b=a.x; for(int i=0;i<%d;i++){ b=b*b-0.25+a.y; } o=vec4(a.x+b,a.y,a.z,a.w); }\n", fq, nv, nv, alu);
        q += snprintf(vs + q, sizeof vs - q, "#version 300 es\nin vec2 p;\n%sout vec4 v[%d];\nvoid main(){ for(int i=0;i<%d;i++) v[i]=vec4(p.x*float(i+1),p.y,p.x+p.y,float(i)); gl_Position=vec4(p,0.0,1.0); }\n", fq, nv, nv);
    } else {
        o += snprintf(fs + o, sizeof fs - o,
            "#version 300 es\nprecision highp float;\nuniform float u;\nin vec2 v;\nout vec4 o;\n"
            "void main(){ float a=v.x+u, b=v.y; for(int i=0;i<%d;i++){ a=a*b+0.5; b=b*a-0.25; } %s%s o=vec4(a,b,u,0.5); }\n", alu, getenv("RASTER_DISCARD") ? "if (a < -1.0e30) discard; " : "", getenv("RASTER_DEPTH") ? "gl_FragDepth = v.x * 0.5; " : "");
        snprintf(vs, sizeof vs, "#version 300 es\nin vec2 p;\nout vec2 v;\nvoid main(){ v=p*0.5+0.5; gl_Position=vec4(p,0.0,1.0); }\n");
    }
    GLuint prog = glCreateProgram();
    glAttachShader(prog, compile(GL_VERTEX_SHADER, vs)); glAttachShader(prog, compile(GL_FRAGMENT_SHADER, fs));
    glLinkProgram(prog); glUseProgram(prog);
    glUniform1f(glGetUniformLocation(prog, "u"), 0.1f);

    /* geometry: tris==0 -> one full quad; else a g x g grid of small triangle pairs tiling the target, ~tris triangles */
    int ntri; float *vb;
    if (tris <= 0) {
        static const float q[] = {-1,-1, 1,-1, -1,1, 1,-1, 1,1, -1,1};
        ntri = 2; vb = malloc(sizeof q); memcpy(vb, q, sizeof q);
    } else {
        int g = 1; while (2 * g * g < tris) g++;
        ntri = 2 * g * g; vb = malloc((size_t)ntri * 6 * sizeof(float));
        float s = 2.0f / g; float *w = vb;
        for (int y = 0; y < g; y++) for (int x = 0; x < g; x++) {
            float x0 = -1 + x * s, y0 = -1 + y * s, x1 = x0 + s, y1 = y0 + s;
            float t[] = {x0,y0, x1,y0, x0,y1, x1,y0, x1,y1, x0,y1};
            memcpy(w, t, sizeof t); w += 12;
        }
    }
    GLuint vao, vbo; glGenVertexArrays(1, &vao); glBindVertexArray(vao);
    glGenBuffers(1, &vbo); glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, (long)ntri * 6 * sizeof(float), vb, GL_STATIC_DRAW);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, 0); glEnableVertexAttribArray(0);

    GLuint fbo, rb; glGenFramebuffers(1, &fbo); glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glGenRenderbuffers(1, &rb); glBindRenderbuffer(GL_RENDERBUFFER, rb);
    glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples <= 1 ? 0 : samples, GL_RGBA8, W, H);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, rb);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) fail("fbo incomplete");
    if (getenv("RASTER_DEPTH")) { GLuint db; glGenRenderbuffers(1, &db); glBindRenderbuffer(GL_RENDERBUFFER, db); glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples <= 1 ? 0 : samples, GL_DEPTH24_STENCIL8, W, H);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, db); glEnable(GL_DEPTH_TEST); }
    glViewport(0, 0, W, H);
    if (blend) { glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA); } else glDisable(GL_BLEND);

    GLenum att = GL_COLOR_ATTACHMENT0;
    double best = 1e30, sum = 0; int reps = 5;
    for (int r = 0; r < reps + 1; r++) {
        double t0 = now();
        for (int f = 0; f < frames; f++) {
            glClearColor(0, 0, 0, 1); glClear(getenv("RASTER_DEPTH") ? (GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT) : GL_COLOR_BUFFER_BIT);
            for (int l = 0; l < layers; l++) glDrawArrays(GL_TRIANGLES, 0, ntri * 3);
            if (getenv("RASTER_FLUSH")) glFlush();
            if (!getenv("RASTER_KEEP")) glInvalidateFramebuffer(GL_FRAMEBUFFER, 1, &att);   /* default: tile store skipped */
        }
        glFinish();
        if (samples <= 1) { unsigned char px[4]; glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px); }
        double dt = (now() - t0) / frames;
        if (r == 0) continue;                                   /* warm-up (shader compile, first touch) */
        sum += dt; if (dt < best) best = dt;
    }
    { GLenum e = glGetError(); if (e != GL_NO_ERROR) { fprintf(stderr, "glError 0x%x\n", e); fail("gl error"); } }
    printf("{\"W\":%d,\"H\":%d,\"layers\":%d,\"alu\":%d,\"blend\":%d,\"samples\":%d,\"tris\":%d,\"frames\":%d,"
           "\"ms_best\":%.4f,\"ms_mean\":%.4f}\n", W, H, layers, alu, blend, samples, ntri, frames, best, sum / reps);
    return 0;
}
