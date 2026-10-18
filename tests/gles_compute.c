#define _POSIX_C_SOURCE 200809L
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl32.h>
#include <drm/drm.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

/* Runtime entry points: no GLES development library or vendor modifications. */
#define EGL_FUNCS(X) \
 X(PFNEGLGETPLATFORMDISPLAYPROC, eglGetPlatformDisplay) \
 X(PFNEGLINITIALIZEPROC, eglInitialize) \
 X(PFNEGLBINDAPIPROC, eglBindAPI) \
 X(PFNEGLCHOOSECONFIGPROC, eglChooseConfig) \
 X(PFNEGLCREATECONTEXTPROC, eglCreateContext) \
 X(PFNEGLMAKECURRENTPROC, eglMakeCurrent) \
 X(PFNEGLDESTROYCONTEXTPROC, eglDestroyContext) \
 X(PFNEGLTERMINATEPROC, eglTerminate) \
 X(PFNEGLGETERRORPROC, eglGetError) \
 X(PFNEGLQUERYSTRINGPROC, eglQueryString) \
 X(PFNEGLQUERYDISPLAYATTRIBEXTPROC, eglQueryDisplayAttribEXT) \
 X(PFNEGLQUERYDEVICESTRINGEXTPROC, eglQueryDeviceStringEXT)
#define GL_FUNCS(X) \
 X(PFNGLGETSTRINGPROC, glGetString) \
 X(PFNGLGETINTEGERVPROC, glGetIntegerv) \
 X(PFNGLGETINTEGERI_VPROC, glGetIntegeri_v) \
 X(PFNGLGETERRORPROC, glGetError) \
 X(PFNGLCREATESHADERPROC, glCreateShader) \
 X(PFNGLSHADERSOURCEPROC, glShaderSource) \
 X(PFNGLCOMPILESHADERPROC, glCompileShader) \
 X(PFNGLGETSHADERIVPROC, glGetShaderiv) \
 X(PFNGLGETSHADERINFOLOGPROC, glGetShaderInfoLog) \
 X(PFNGLCREATEPROGRAMPROC, glCreateProgram) \
 X(PFNGLATTACHSHADERPROC, glAttachShader) \
 X(PFNGLLINKPROGRAMPROC, glLinkProgram) \
 X(PFNGLGETPROGRAMIVPROC, glGetProgramiv) \
 X(PFNGLGETPROGRAMINFOLOGPROC, glGetProgramInfoLog) \
 X(PFNGLGENBUFFERSPROC, glGenBuffers) \
 X(PFNGLBINDBUFFERPROC, glBindBuffer) \
 X(PFNGLBUFFERDATAPROC, glBufferData) \
 X(PFNGLBINDBUFFERBASEPROC, glBindBufferBase) \
 X(PFNGLUSEPROGRAMPROC, glUseProgram) \
 X(PFNGLGETUNIFORMLOCATIONPROC, glGetUniformLocation) \
 X(PFNGLUNIFORM1UIPROC, glUniform1ui) \
 X(PFNGLDISPATCHCOMPUTEPROC, glDispatchCompute) \
 X(PFNGLMEMORYBARRIERPROC, glMemoryBarrier) \
 X(PFNGLFENCESYNCPROC, glFenceSync) \
 X(PFNGLCLIENTWAITSYNCPROC, glClientWaitSync) \
 X(PFNGLMAPBUFFERRANGEPROC, glMapBufferRange) \
 X(PFNGLUNMAPBUFFERPROC, glUnmapBuffer) \
 X(PFNGLDELETESYNCPROC, glDeleteSync) \
 X(PFNGLDELETEBUFFERSPROC, glDeleteBuffers) \
 X(PFNGLDELETEPROGRAMPROC, glDeleteProgram) \
 X(PFNGLDELETESHADERPROC, glDeleteShader) \
 X(PFNGLGENTEXTURESPROC, glGenTextures) \
 X(PFNGLBINDTEXTUREPROC, glBindTexture) \
 X(PFNGLTEXSTORAGE2DPROC, glTexStorage2D) \
 X(PFNGLTEXSUBIMAGE2DPROC, glTexSubImage2D) \
 X(PFNGLTEXPARAMETERIPROC, glTexParameteri) \
 X(PFNGLACTIVETEXTUREPROC, glActiveTexture) \
 X(PFNGLBINDIMAGETEXTUREPROC, glBindImageTexture) \
 X(PFNGLPIXELSTOREIPROC, glPixelStorei)
#define DECL(type, name) static type p_##name;
EGL_FUNCS(DECL)
GL_FUNCS(DECL)
static void fail(const char *stage) { fprintf(stderr, "FAIL stage=%s\n", stage); exit(1); }
static void egl_ok(EGLBoolean ok, const char *stage) {
    EGLint error = p_eglGetError();
    printf("egl stage=%s ok=%u error=0x%x\n", stage, ok, error);
    if (!ok || error != EGL_SUCCESS) fail(stage);
}
static void gl_ok(const char *stage) {
    GLenum error = p_glGetError();
    printf("gl stage=%s error=0x%x\n", stage, error);
    if (error != GL_NO_ERROR) fail(stage);
}
static double monotonic(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) fail("clock");
    return ts.tv_sec + ts.tv_nsec / 1e9;
}
static void save(const char *name, const void *bytes, size_t length) {
    FILE *f = fopen(name, "wb");
    if (!f) fail("artifact-open");
    if (fwrite(bytes, 1, length, f) != length) fail("artifact-write");
    if (fclose(f)) fail("artifact-close");
}
static void readback(GLuint buffer, size_t words, const char *name) {
    p_glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffer);
    gl_ok("readback-bind");
    const void *ptr = p_glMapBufferRange(GL_SHADER_STORAGE_BUFFER, 0,
                                       (GLsizeiptr)(words * 4), GL_MAP_READ_BIT);
    gl_ok("map");
    if (!ptr) fail("map-null");
    /* Copy to owned host bytes before unmapping. No expected-data writes here. */
    void *copy = malloc(words * 4);
    if (!copy) fail("readback-allocation");
    memcpy(copy, ptr, words * 4);
    GLboolean ok = p_glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
    printf("unmap valid=%u\n", ok);
    gl_ok("unmap");
    if (!ok) fail("unmap-invalid-data");
    save(name, copy, words * 4);
    free(copy);
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc != 4) { fprintf(stderr, "usage: %s control|constant|index|invalid|private count render-node\n", argv[0]); return 2; }
    const char *mode = argv[1], *expected_node = argv[3];
    if (strcmp(mode, "control") && strcmp(mode, "constant") && strcmp(mode, "index") && strcmp(mode, "invalid") && strcmp(mode, "private")) return 2;
    char *end = NULL;
    unsigned long parsed = strtoul(argv[2], &end, 10);
    if (!*argv[2] || *end || parsed < 1 || parsed > 262144) return 2;
    unsigned n = (unsigned)parsed, groups = (n + 31) / 32, words = 8 + groups * 32 + 8;
    printf("case mode=%s count=%u groups=%u local_size=32 words=%u byte_order=native\n", mode, n, groups, words);
    void *egl = dlopen("libEGL.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!egl) { fprintf(stderr, "%s\n", dlerror()); fail("dlopen-EGL"); }
    PFNEGLGETPROCADDRESSPROC get = (PFNEGLGETPROCADDRESSPROC)dlsym(egl, "eglGetProcAddress");
    if (!get) fail("get-proc-address");
#define LOAD(type, name) p_##name = (type)get(#name); if (!p_##name) fail(#name "-missing");
    EGL_FUNCS(LOAD)
    GL_FUNCS(LOAD)
    EGLDisplay display = p_eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
    if (display == EGL_NO_DISPLAY) fail("platform-display");
    EGLint major, minor;
    egl_ok(p_eglInitialize(display, &major, &minor), "initialize");
    printf("egl_version=%d.%d egl_vendor=%s\n", major, minor, p_eglQueryString(display, EGL_VENDOR));
    EGLAttrib device = 0;
    egl_ok(p_eglQueryDisplayAttribEXT(display, EGL_DEVICE_EXT, &device), "display-device");
    const char *node = p_eglQueryDeviceStringEXT((EGLDeviceEXT)device, EGL_DRM_RENDER_NODE_FILE_EXT);
    const char *card = p_eglQueryDeviceStringEXT((EGLDeviceEXT)device, EGL_DRM_DEVICE_FILE_EXT);
    printf("egl_render_node=%s egl_card=%s\n", node ? node : "NULL", card ? card : "NULL");
    if (!node || strcmp(node, expected_node)) fail("render-node-identity");
    int fd = open(node, O_RDWR | O_CLOEXEC);
    if (fd < 0) fail("DRM-open");
    char driver[128] = {0}, description[256] = {0};
    struct drm_version version = {.name_len = sizeof(driver)-1, .name = driver,
        .desc_len = sizeof(description)-1, .desc = description};
    if (ioctl(fd, DRM_IOCTL_VERSION, &version)) fail("DRM-version");
    printf("drm_driver=%s drm_description=%s drm_version=%d.%d.%d\n", driver, description,
           version.version_major, version.version_minor, version.version_patchlevel);
    close(fd);
    if (strcmp(driver, "asahi")) fail("DRM-driver-identity");
    egl_ok(p_eglBindAPI(EGL_OPENGL_ES_API), "bind-ES");
    EGLint config_attrs[] = {EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RED_SIZE, 8, EGL_NONE};
    EGLConfig config;
    EGLint configs = 0;
    egl_ok(p_eglChooseConfig(display, config_attrs, &config, 1, &configs), "choose-config");
    if (configs != 1) fail("config-count");
    EGLint context_attrs[] = {EGL_CONTEXT_MAJOR_VERSION, 3, EGL_CONTEXT_MINOR_VERSION, 2, EGL_NONE};
    EGLContext context = p_eglCreateContext(display, config, EGL_NO_CONTEXT, context_attrs);
    egl_ok(context != EGL_NO_CONTEXT, "create-ES32");
    egl_ok(p_eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, context), "make-current");
    const char *renderer = (const char *)p_glGetString(GL_RENDERER);
    printf("gl_renderer=%s\ngl_vendor=%s\ngl_version=%s\nglsl_version=%s\n", renderer ? renderer : "NULL",
        p_glGetString(GL_VENDOR), p_glGetString(GL_VERSION), p_glGetString(GL_SHADING_LANGUAGE_VERSION));
    if (!renderer || strcmp(renderer, "Apple M2 Max (G14C B1)")) fail("hardware-renderer-identity");
    GLint glmajor, glminor, invocations, size, count;
    p_glGetIntegerv(GL_MAJOR_VERSION, &glmajor); p_glGetIntegerv(GL_MINOR_VERSION, &glminor);
    p_glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS, &invocations);
    p_glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_SIZE, 0, &size);
    p_glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT, 0, &count);
    printf("limits gl=%d.%d invocations=%d size_x=%d count_x=%d\n", glmajor, glminor, invocations, size, count);
    gl_ok("identity-limits");
    if (glmajor < 3 || (glmajor == 3 && glminor < 2) || invocations < 32 || size < 32 || count < (GLint)groups) fail("capabilities");
    static char source[1 << 16];
    const char *expression = !strcmp(mode, "index") ? "(i * 0x9e3779b9u) ^ 0x12345678u" : "0x12345678u";
    if (!strcmp(mode, "invalid")) expression = "INTENTIONAL_UNDECLARED_IDENTIFIER";
    /* "private": a dynamically indexed 1024-entry private array, which Mesa places in scratch (stack) memory. */
    const char *prelude = "";
    if (!strcmp(mode, "private")) {
        prelude = "uint pick(uint i) { uint a[1024]; for (uint k=0u; k<1024u; k++) a[k] = (i*k) ^ (0x1234u*k); "
                  "return a[(i*7u)&1023u] + a[(i*13u+5u)&1023u]; }\n";
        expression = "pick(i)";
    }
    int length = snprintf(source, sizeof(source),
        "#version 320 es\nprecision highp int;\nlayout(local_size_x=32, local_size_y=1, local_size_z=1) in;\n"
        "layout(std430, binding=0) buffer Output { uint data[]; };\nuniform uint count;\n%s"
        "void main() { uint i=gl_GlobalInvocationID.x; if (i < count) data[8u+i]=%s; }\n", prelude, expression);
    if (length < 0 || (size_t)length >= sizeof(source)) fail("shader-source-size");
    /* GLES_SHADER_FILE: replace the generated shader by the contents of this file (same interface: local_size_x = 32,
     * `data[8u + i]` outputs in binding 0, `uniform uint count`). Used by scripts/run_gles_stack2.py. */
    if (getenv("GLES_SHADER_FILE")) {
        FILE *sf = fopen(getenv("GLES_SHADER_FILE"), "rb");
        if (!sf) fail("shader-file-open");
        size_t got = fread(source, 1, sizeof(source) - 1, sf);
        if (!feof(sf) || got == 0) fail("shader-file-read");
        fclose(sf); source[got] = 0; length = (int)got;
    }
    save("shader.comp", source, (size_t)length);
    GLuint shader = p_glCreateShader(GL_COMPUTE_SHADER);
    const GLchar *source_ptr = source;
    p_glShaderSource(shader, 1, &source_ptr, NULL); p_glCompileShader(shader);
    GLint compiled, log_length;
    p_glGetShaderiv(shader, GL_COMPILE_STATUS, &compiled);
    p_glGetShaderiv(shader, GL_INFO_LOG_LENGTH, &log_length);
    if (log_length < 0 || log_length > 1048576) fail("compile-log-size");
    char *log = calloc((size_t)log_length + 1, 1);
    if (!log) fail("compile-log-allocation");
    if (log_length) p_glGetShaderInfoLog(shader, log_length, NULL, log);
    save("compile.log", log, strlen(log)); free(log);
    printf("compile_status=%d\n", compiled); gl_ok("compile");
    if (!compiled) { fprintf(stderr, "FAIL stage=shader-compile\n"); return 3; }
    if (!strcmp(mode, "invalid")) fail("invalid-shader-accepted");
    GLuint program = p_glCreateProgram(); p_glAttachShader(program, shader); p_glLinkProgram(program);
    GLint linked;
    p_glGetProgramiv(program, GL_LINK_STATUS, &linked);
    p_glGetProgramiv(program, GL_INFO_LOG_LENGTH, &log_length);
    if (log_length < 0 || log_length > 1048576) fail("link-log-size");
    log = calloc((size_t)log_length + 1, 1);
    if (!log) fail("link-log-allocation");
    if (log_length) p_glGetProgramInfoLog(program, log_length, NULL, log);
    save("link.log", log, strlen(log)); free(log);
    printf("link_status=%d\n", linked); gl_ok("link");
    if (!linked) fail("shader-link");
    uint32_t *input = malloc(sizeof(uint32_t) * words), control[16];
    if (!input) fail("input-allocation");
    for (unsigned i=0; i<words; i++) input[i] = 0xcdcdcdcdu;
    for (unsigned i=0; i<16; i++) control[i] = 0xa5a50000u + i;
    save("input.bin", input, words * 4); save("control-input.bin", control, sizeof(control));
    GLuint buffers[2]; p_glGenBuffers(2, buffers);
    p_glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffers[0]);
    p_glBufferData(GL_SHADER_STORAGE_BUFFER, words * 4, input, GL_DYNAMIC_COPY);
    p_glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, buffers[0]);
    p_glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffers[1]);
    p_glBufferData(GL_SHADER_STORAGE_BUFFER, sizeof(control), control, GL_DYNAMIC_COPY);
    p_glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, buffers[1]);
    /* GLES_TEX_FORMAT (r8 rgba8 r8snorm rgba8snorm rgba8srgb r16f r32f rgba32f r8ui r32ui), GLES_TEX_W / GLES_TEX_H, GLES_TEX_DATA (raw file),
     * GLES_TEX_FILTER (nearest | linear), GLES_TEX_WRAP (clamp | repeat | mirror), GLES_TEX_IMAGE=1 (also bind level 0 as read-write image unit 0).
     * The texture is bound to texture unit 0 (use `layout(binding=0)` in the shader). Used by scripts/run_gles_texture.py. */
    if (getenv("GLES_TEX_FORMAT")) {
        static const struct { const char *name; GLenum internal, format, type; unsigned bpp; } fmts[] = {
            {"r8", GL_R8, GL_RED, GL_UNSIGNED_BYTE, 1}, {"rgba8", GL_RGBA8, GL_RGBA, GL_UNSIGNED_BYTE, 4},
            {"r8snorm", GL_R8_SNORM, GL_RED, GL_BYTE, 1}, {"rgba8snorm", GL_RGBA8_SNORM, GL_RGBA, GL_BYTE, 4},
            {"rgba8srgb", GL_SRGB8_ALPHA8, GL_RGBA, GL_UNSIGNED_BYTE, 4}, {"r16f", GL_R16F, GL_RED, GL_HALF_FLOAT, 2},
            {"r32f", GL_R32F, GL_RED, GL_FLOAT, 4}, {"rgba32f", GL_RGBA32F, GL_RGBA, GL_FLOAT, 16},
            {"r8ui", GL_R8UI, GL_RED_INTEGER, GL_UNSIGNED_BYTE, 1}, {"r32ui", GL_R32UI, GL_RED_INTEGER, GL_UNSIGNED_INT, 4}};
        const char *fn = getenv("GLES_TEX_FORMAT");
        int fi = -1;
        for (unsigned k = 0; k < sizeof fmts / sizeof *fmts; k++) if (!strcmp(fn, fmts[k].name)) fi = (int)k;
        if (fi < 0) fail("tex-format");
        unsigned tw = (unsigned)atoi(getenv("GLES_TEX_W") ? getenv("GLES_TEX_W") : "16"), th = (unsigned)atoi(getenv("GLES_TEX_H") ? getenv("GLES_TEX_H") : "16");
        if (!tw || !th || tw > 4096 || th > 4096) fail("tex-size");
        size_t bytes = (size_t)tw * th * fmts[fi].bpp;
        void *pix = calloc(1, bytes);
        if (!pix) fail("tex-alloc");
        if (getenv("GLES_TEX_DATA")) {
            FILE *tf = fopen(getenv("GLES_TEX_DATA"), "rb");
            if (!tf) fail("tex-data-open");
            if (fread(pix, 1, bytes, tf) != bytes) fail("tex-data-read");
            fclose(tf);
        }
        GLuint tex;
        p_glGenTextures(1, &tex);
        p_glActiveTexture(GL_TEXTURE0);
        p_glBindTexture(GL_TEXTURE_2D, tex);
        p_glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        p_glTexStorage2D(GL_TEXTURE_2D, 1, fmts[fi].internal, (GLsizei)tw, (GLsizei)th);
        p_glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, (GLsizei)tw, (GLsizei)th, fmts[fi].format, fmts[fi].type, pix);
        const char *flt = getenv("GLES_TEX_FILTER"), *wrp = getenv("GLES_TEX_WRAP");
        GLint f = (flt && !strcmp(flt, "linear")) ? GL_LINEAR : GL_NEAREST;
        GLint wr = (wrp && !strcmp(wrp, "repeat")) ? GL_REPEAT : (wrp && !strcmp(wrp, "mirror")) ? GL_MIRRORED_REPEAT : GL_CLAMP_TO_EDGE;
        p_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, f); p_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, f);
        p_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wr); p_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wr);
        if (getenv("GLES_TEX_IMAGE")) p_glBindImageTexture(0, tex, 0, GL_FALSE, 0, GL_READ_WRITE, fmts[fi].internal);
        gl_ok("texture-setup");
        free(pix);
    }
    p_glUseProgram(program);
    GLint location = p_glGetUniformLocation(program, "count");
    if (location < 0) fail("count-uniform");
    p_glUniform1ui(location, n); gl_ok("buffers-program-uniform");
    int dispatch = strcmp(mode, "control") != 0;
    printf("dispatch_count=%d\n", dispatch);
    if (dispatch) p_glDispatchCompute(groups, 1, 1);
    p_glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT | GL_BUFFER_UPDATE_BARRIER_BIT);
    gl_ok("dispatch-barrier");
    GLsync fence = p_glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    gl_ok("fence-create");
    if (!fence) fail("fence-null");
    double start = monotonic(), deadline = start + 5.0;
    GLenum status = GL_TIMEOUT_EXPIRED;
    unsigned waits = 0;
    while (monotonic() < deadline && waits < 100) {
        status = p_glClientWaitSync(fence, GL_SYNC_FLUSH_COMMANDS_BIT, 50000000ull);
        ++waits;
        printf("fence_wait=%u status=0x%x elapsed_s=%.6f\n", waits, status, monotonic()-start);
        gl_ok("fence-wait");
        if (status == GL_ALREADY_SIGNALED || status == GL_CONDITION_SATISFIED) break;
        if (status != GL_TIMEOUT_EXPIRED) fail("fence-wait-failed");
    }
    if (status != GL_ALREADY_SIGNALED && status != GL_CONDITION_SATISFIED) fail("fence-deadline");
    readback(buffers[0], words, "output.bin"); readback(buffers[1], 16, "control-output.bin");
    p_glDeleteSync(fence); p_glDeleteBuffers(2, buffers);
    p_glDeleteProgram(program); p_glDeleteShader(shader); gl_ok("GL-cleanup");
    egl_ok(p_eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT), "release-current");
    egl_ok(p_eglDestroyContext(display, context), "destroy-context");
    egl_ok(p_eglTerminate(display), "terminate"); dlclose(egl);
    puts("READBACK_COMPLETE (host oracle is performed by run_compute.py)");
    return 0;
}
