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
 X(PFNGLREADPIXELSPROC, glReadPixels) X(PFNGLBLITFRAMEBUFFERPROC, glBlitFramebuffer) X(PFNGLGENTEXTURESPROC, glGenTextures) X(PFNGLBINDTEXTUREPROC, glBindTexture) X(PFNGLTEXSTORAGE2DPROC, glTexStorage2D) X(PFNGLTEXSUBIMAGE2DPROC, glTexSubImage2D) X(PFNGLFRAMEBUFFERTEXTURE2DPROC, glFramebufferTexture2D) X(PFNGLTEXPARAMETERIPROC, glTexParameteri) X(PFNGLFLUSHPROC, glFlush) X(PFNGLFLUSHPROC, glFlush) X(PFNGLINVALIDATEFRAMEBUFFERPROC, glInvalidateFramebuffer) X(PFNGLGETERRORPROC, glGetError)
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
#define glTexParameteri p_glTexParameteri
#define glFramebufferTexture2D p_glFramebufferTexture2D
#define glTexSubImage2D p_glTexSubImage2D
#define glTexStorage2D p_glTexStorage2D
#define glBindTexture p_glBindTexture
#define glGenTextures p_glGenTextures
#define glBlitFramebuffer p_glBlitFramebuffer
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


/* Blit probe: RGBA8 source texture with a known pattern -> glBlitFramebuffer to another RGBA8 texture (sizes SW x SH -> DW x DH, filter nearest/linear)
 * -> read back DW x DH x 4 bytes to out. usage: gles_blit SW SH DW DH filter(0 nearest, 1 linear) src.bin(out) dst.bin(out) [flip] */
int main(int argc, char **argv) {
    if (argc < 8) { fprintf(stderr, "usage\n"); return 2; }
    int SW = atoi(argv[1]), SH = atoi(argv[2]), DW = atoi(argv[3]), DH = atoi(argv[4]), lin = atoi(argv[5]); int flip = argc > 8;
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
    unsigned char *src = malloc((size_t)SW * SH * 4);
    for (int y = 0; y < SH; y++) for (int x = 0; x < SW; x++) { unsigned char *p = src + ((size_t)y * SW + x) * 4; p[0] = (x * 255) / (SW > 1 ? SW - 1 : 1); p[1] = (y * 255) / (SH > 1 ? SH - 1 : 1); p[2] = (x * 7 + y * 13) & 255; p[3] = 255 - ((x + y) & 63); }
    GLuint tex[2]; glGenTextures(2, tex);
    glBindTexture(GL_TEXTURE_2D, tex[0]); glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, SW, SH); glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, SW, SH, GL_RGBA, GL_UNSIGNED_BYTE, src);
    glBindTexture(GL_TEXTURE_2D, tex[1]); glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, DW, DH);
    GLuint fb[2]; glGenFramebuffers(2, fb);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, fb[0]); glFramebufferTexture2D(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex[0], 0);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, fb[1]); glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex[1], 0);
    glClearColor(0.5f, 0.25f, 0.125f, 1.0f); glClear(GL_COLOR_BUFFER_BIT);
    glBlitFramebuffer(0, 0, SW, SH, 0, flip ? DH : 0, DW, flip ? 0 : DH, GL_COLOR_BUFFER_BIT, lin ? GL_LINEAR : GL_NEAREST);
    if (getenv("BLIT_TIME")) {   /* BLIT_TIME=frames: time back-to-back blits (a 1-pixel read ends each repetition) */
        int frames = atoi(getenv("BLIT_TIME")); double best = 1e30; unsigned char px[4];
        for (int r = 0; r < 6; r++) {
            struct timespec a, b; clock_gettime(CLOCK_MONOTONIC, &a);
            glBindFramebuffer(GL_READ_FRAMEBUFFER, fb[0]); for (int f = 0; f < frames; f++) { glBlitFramebuffer(0, 0, SW, SH, 0, 0, DW, DH, GL_COLOR_BUFFER_BIT, lin ? GL_LINEAR : GL_NEAREST); p_glFlush(); }
            glBindFramebuffer(GL_READ_FRAMEBUFFER, fb[1]); glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
            clock_gettime(CLOCK_MONOTONIC, &b); double dt = ((b.tv_sec - a.tv_sec) * 1e3 + (b.tv_nsec - a.tv_nsec) * 1e-6) / frames; if (r > 0 && dt < best) best = dt;
        }
        fprintf(stderr, "{\"blit_ms\":%.4f}\n", best);
    }
    glBindFramebuffer(GL_READ_FRAMEBUFFER, fb[1]);
    unsigned char *dst = malloc((size_t)DW * DH * 4); glReadPixels(0, 0, DW, DH, GL_RGBA, GL_UNSIGNED_BYTE, dst);
    { GLenum e = glGetError(); if (e) { fprintf(stderr, "glError 0x%x\n", e); fail("gl error"); } }
    FILE *f = fopen(argv[6], "wb"); fwrite(src, 4, (size_t)SW * SH, f); fclose(f); f = fopen(argv[7], "wb"); fwrite(dst, 4, (size_t)DW * DH, f); fclose(f);
    printf("{\"SW\":%d,\"SH\":%d,\"DW\":%d,\"DH\":%d,\"linear\":%d}\n", SW, SH, DW, DH, lin);
    return 0;
}
