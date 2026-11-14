/* (shared loader from gles_raster.c) Render-path timing probe (surfaceless EGL, GLES 3.x through Mesa's open-source asahi driver).
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
 X(PFNGLREADPIXELSPROC, glReadPixels) X(PFNGLFLUSHPROC, glFlush) X(PFNGLINVALIDATEFRAMEBUFFERPROC, glInvalidateFramebuffer) X(PFNGLBLITFRAMEBUFFERPROC, glBlitFramebuffer) X(PFNGLGENTEXTURESPROC, glGenTextures) X(PFNGLBINDTEXTUREPROC, glBindTexture) X(PFNGLTEXSTORAGE2DPROC, glTexStorage2D) X(PFNGLFRAMEBUFFERTEXTURE2DPROC, glFramebufferTexture2D) X(PFNGLREADBUFFERPROC, glReadBuffer) X(PFNGLBINDATTRIBLOCATIONPROC, glBindAttribLocation) X(PFNGLGETERRORPROC, glGetError)
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
#define glBlitFramebuffer p_glBlitFramebuffer
#define glGenTextures p_glGenTextures
#define glBindTexture p_glBindTexture
#define glTexStorage2D p_glTexStorage2D
#define glFramebufferTexture2D p_glFramebufferTexture2D
#define glReadBuffer p_glReadBuffer
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


/* Varying-interpolation readback probe: renders ONE triangle whose vertices carry arbitrary clip positions (w != 1 allowed)
 * and arbitrary attribute values, into an RGBA32F target (optionally 4x MSAA, resolved by blit), and writes the W*H*4 floats.
 * usage: gles_varying W H mode samples out.f32 [x0 y0 w0 x1 y1 w1 x2 y2 w2]
 *   mode 0 smooth, 1 noperspective(unsupported in ES: emulated by w=1), 2 flat, 3 centroid.
 * The fragment shader outputs vec4(a, b, c, d) = four varyings with distinct per-vertex values. */
int main(int argc, char **argv) {
    if (argc < 6) { fprintf(stderr, "usage\n"); return 2; }
    int W = atoi(argv[1]), H = atoi(argv[2]), mode = atoi(argv[3]), samples = atoi(argv[4]); const char *out = argv[5];
    float P[9] = {-0.9f,-0.8f,1.0f, 0.8f,-0.7f,1.0f, -0.2f,0.9f,1.0f};
    for (int i = 0; i < 9 && 6 + i < argc; i++) P[i] = (float)atof(argv[6 + i]);
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
    EGLint cx[] = {EGL_CONTEXT_MAJOR_VERSION, 3, EGL_CONTEXT_MINOR_VERSION, 2, EGL_NONE};
    EGLContext c = p_eglCreateContext(d, cfg, EGL_NO_CONTEXT, cx); if (!c) fail("context");
    if (!p_eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, c)) fail("makecurrent");
    const char *qual = mode == 2 ? "flat " : mode == 3 ? "centroid " : "";
    char vs[2048], fs[2048];
    snprintf(vs, sizeof vs, "#version 320 es\nin vec4 p;\nin vec4 q;\n%sout vec4 va;\n%sout vec2 vb;\nvoid main(){ va=q; vb=q.zw*3.0+1.0; gl_Position=p; }\n", qual, qual);
    snprintf(fs, sizeof fs, "#version 320 es\nprecision highp float;\n%sin vec4 va;\n%sin vec2 vb;\nout vec4 o;\nvoid main(){ o=vec4(va.x, va.y, vb.x, vb.y+va.w); }\n", qual, qual);
    if (getenv("VARY_FS")) snprintf(fs, sizeof fs, "%s", getenv("VARY_FS"));   /* full replacement fragment shader */
    GLuint prog = glCreateProgram();
    glAttachShader(prog, compile(GL_VERTEX_SHADER, vs)); glAttachShader(prog, compile(GL_FRAGMENT_SHADER, fs));
    p_glBindAttribLocation(prog, 0, "p"); p_glBindAttribLocation(prog, 1, "q");
    glLinkProgram(prog); glUseProgram(prog);
    float vb[3 * 8];
    float Q[3][4] = {{0.25f, 1.5f, -2.0f, 0.125f}, {-1.25f, 0.5f, 3.0f, 0.75f}, {0.75f, -3.0f, 0.5f, -1.5f}};
    for (int v = 0; v < 3; v++) {
        vb[v*8+0] = P[v*3+0] * P[v*3+2]; vb[v*8+1] = P[v*3+1] * P[v*3+2]; vb[v*8+2] = 0; vb[v*8+3] = P[v*3+2];
        for (int k = 0; k < 4; k++) vb[v*8+4+k] = Q[v][k];
    }
    GLuint vao, vbo; glGenVertexArrays(1, &vao); glBindVertexArray(vao);
    glGenBuffers(1, &vbo); glBindBuffer(GL_ARRAY_BUFFER, vbo); glBufferData(GL_ARRAY_BUFFER, sizeof vb, vb, GL_STATIC_DRAW);
    glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 32, (void *)0); glEnableVertexAttribArray(0);
    glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 32, (void *)16); glEnableVertexAttribArray(1);
    GLuint fbo, rb, rfbo, tex; glGenFramebuffers(1, &fbo); glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glGenRenderbuffers(1, &rb); glBindRenderbuffer(GL_RENDERBUFFER, rb);
    int u8 = getenv("VARY_RGBA8") != NULL;   /* RGBA8 target + byte readback: checks the tile store conversion */
    glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples <= 1 ? 0 : samples, u8 ? GL_RGBA8 : GL_RGBA32F, W, H);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, rb);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) fail("fbo incomplete (RGBA32F)");
    if (getenv("VARY_DEPTH")) { GLuint db; glGenRenderbuffers(1, &db); glBindRenderbuffer(GL_RENDERBUFFER, db); glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples <= 1 ? 0 : samples, GL_DEPTH24_STENCIL8, W, H); glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, db); p_glEnable(GL_DEPTH_TEST); }
    glViewport(0, 0, W, H); glClearColor(-777, -777, -777, -777); glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLES, 0, 3);
    GLuint src = fbo;
    if (samples > 1) {
        glGenTextures(1, &tex); glBindTexture(GL_TEXTURE_2D, tex); glTexStorage2D(GL_TEXTURE_2D, 1, u8 ? GL_RGBA8 : GL_RGBA32F, W, H);
        glGenFramebuffers(1, &rfbo); glBindFramebuffer(GL_FRAMEBUFFER, rfbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo); glBindFramebuffer(GL_DRAW_FRAMEBUFFER, rfbo);
        glBlitFramebuffer(0, 0, W, H, 0, 0, W, H, GL_COLOR_BUFFER_BIT, GL_NEAREST); src = rfbo;
    }
    glBindFramebuffer(GL_READ_FRAMEBUFFER, src);
    float *img = malloc((size_t)W * H * 16);
    if (u8) glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, img); else glReadPixels(0, 0, W, H, GL_RGBA, GL_FLOAT, img);
    { GLenum e = glGetError(); if (e) { fprintf(stderr, "glError 0x%x\n", e); fail("gl error"); } }
    FILE *f = fopen(out, "wb"); fwrite(img, u8 ? 4 : 16, (size_t)W * H, f); fclose(f);
    printf("{\"W\":%d,\"H\":%d,\"mode\":%d,\"samples\":%d,\"out\":\"%s\"}\n", W, H, mode, samples, out);
    return 0;
}
