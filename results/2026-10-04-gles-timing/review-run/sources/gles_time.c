#define _POSIX_C_SOURCE 200809L
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl32.h>
#include <GLES2/gl2ext.h>
#include <inttypes.h>
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
 X(PFNGLDELETESHADERPROC, glDeleteShader)
#define TIMER_FUNCS(X) \
 X(PFNGLGENQUERIESEXTPROC, glGenQueriesEXT) \
 X(PFNGLDELETEQUERIESEXTPROC, glDeleteQueriesEXT) \
 X(PFNGLBEGINQUERYEXTPROC, glBeginQueryEXT) \
 X(PFNGLENDQUERYEXTPROC, glEndQueryEXT) \
 X(PFNGLQUERYCOUNTEREXTPROC, glQueryCounterEXT) \
 X(PFNGLGETQUERYIVEXTPROC, glGetQueryivEXT) \
 X(PFNGLGETQUERYOBJECTUIVEXTPROC, glGetQueryObjectuivEXT) \
 X(PFNGLGETQUERYOBJECTUI64VEXTPROC, glGetQueryObjectui64vEXT) \
 X(PFNGLGETINTEGER64VPROC, glGetInteger64v) \
 X(PFNGLGETSTRINGIPROC, glGetStringi) \
 X(PFNGLFLUSHPROC, glFlush)
#define DECL(type, name) static type p_##name;
EGL_FUNCS(DECL)
GL_FUNCS(DECL)
TIMER_FUNCS(DECL)
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
    if (argc != 5) { fprintf(stderr, "usage: %s control|empty|empty-pair|elapsed|pair repeats count node\n", argv[0]); return 2; }
    const char *mode = argv[1], *expected_node = argv[4];
    if (strcmp(mode,"control") && strcmp(mode,"empty") && strcmp(mode,"elapsed") && strcmp(mode,"pair") && strcmp(mode,"empty-pair")) return 2;
    char *end;
    unsigned long r = strtoul(argv[2], &end, 10);
    if (!*argv[2] || *end || r > 256) return 2;
    unsigned long count_arg = strtoul(argv[3], &end, 10);
    if (!*argv[3] || *end || count_arg != 64) return 2;
    unsigned n = 64, groups = 2, words = 80, repeats = (unsigned)r;
    printf("case mode=%s repeats=%u count=%u groups=%u local_size=32\n",mode,repeats,n,groups);
    void *egl = dlopen("libEGL.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!egl) { fprintf(stderr, "%s\n", dlerror()); fail("dlopen-EGL"); }
    PFNEGLGETPROCADDRESSPROC get = (PFNEGLGETPROCADDRESSPROC)dlsym(egl, "eglGetProcAddress");
    if (!get) fail("get-proc-address");
#define LOAD(type, name) p_##name = (type)get(#name); if (!p_##name) fail(#name "-missing");
    EGL_FUNCS(LOAD)
    GL_FUNCS(LOAD)
    TIMER_FUNCS(LOAD)
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
    GLint extensions = 0, disjoint_before = -1, elapsed_bits = 0, timestamp_bits = 0;
    p_glGetIntegerv(GL_NUM_EXTENSIONS, &extensions);
    int advertised = 0;
    for (GLint i=0; i<extensions; ++i) {
        const char *ext = (const char *)p_glGetStringi(GL_EXTENSIONS, (GLuint)i);
        if (ext && !strcmp(ext,"GL_EXT_disjoint_timer_query")) advertised = 1;
    }
    if (!advertised) fail("timer-extension-absent");
    p_glGetQueryivEXT(GL_TIME_ELAPSED_EXT,GL_QUERY_COUNTER_BITS_EXT,&elapsed_bits);
    p_glGetQueryivEXT(GL_TIMESTAMP_EXT,GL_QUERY_COUNTER_BITS_EXT,&timestamp_bits);
    gl_ok("timer-capabilities");
    printf("timer_extension=%d elapsed_bits=%d timestamp_bits=%d\n",advertised,elapsed_bits,timestamp_bits);
    if(elapsed_bits > 64 || timestamp_bits > 64) fail("counter-width");
    if ((!strcmp(mode,"elapsed") || !strcmp(mode,"empty")) && elapsed_bits <= 0) fail("elapsed-unsupported");
    if ((!strcmp(mode,"pair") || !strcmp(mode,"empty-pair")) && timestamp_bits <= 0) fail("timestamp-unsupported");
    const char source[] =
        "#version 320 es\nprecision highp int;\nlayout(local_size_x=32) in;\n"
        "layout(std430,binding=0) buffer Output { uint data[]; };\n"
        "layout(std430,binding=2) readonly buffer Seeds { uint seed[]; };\n"
        "uniform uint count; uniform uint repeats;\n"
        "void main() { uint i=gl_GlobalInvocationID.x; if(i<count) { uint x=seed[i];"
        "for(uint j=0u;j<repeats;++j) x=x*1664525u+1013904223u; data[8u+i]=x; } }\n";
    size_t length = sizeof(source)-1;
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
    uint32_t input[80], control[16];
    for (unsigned i=0; i<words; i++) input[i] = 0xcdcdcdcdu;
    for (unsigned i=0; i<16; i++) control[i] = 0xa5a50000u + i;
    save("input.bin", input, words * 4); save("control-input.bin", control, sizeof(control));
    GLuint buffers[3]; p_glGenBuffers(3, buffers);
    p_glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffers[0]);
    p_glBufferData(GL_SHADER_STORAGE_BUFFER, words * 4, input, GL_DYNAMIC_COPY);
    p_glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, buffers[0]);
    p_glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffers[1]);
    p_glBufferData(GL_SHADER_STORAGE_BUFFER, sizeof(control), control, GL_DYNAMIC_COPY);
    p_glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, buffers[1]);
    uint32_t seeds[64];
    for (unsigned i=0;i<64;++i) seeds[i]=0x12345678u ^ (i*0x9e3779b9u);
    save("seeds.bin",seeds,sizeof(seeds));
    p_glBindBuffer(GL_SHADER_STORAGE_BUFFER,buffers[2]);
    p_glBufferData(GL_SHADER_STORAGE_BUFFER,sizeof(seeds),seeds,GL_DYNAMIC_COPY);
    p_glBindBufferBase(GL_SHADER_STORAGE_BUFFER,2,buffers[2]);
    p_glUseProgram(program);
    GLint location = p_glGetUniformLocation(program, "count");
    if (location < 0) fail("count-uniform");
    p_glUniform1ui(location, n); gl_ok("buffers-program-uniform");
    GLint repeat_location = p_glGetUniformLocation(program,"repeats");
    if(repeat_location<0) fail("repeats-uniform");
    p_glUniform1ui(repeat_location,repeats);
    GLuint queries[2] = {0,0};
    int timed = strcmp(mode,"control") != 0, pair = !strcmp(mode,"pair") || !strcmp(mode,"empty-pair");
    if(timed) p_glGenQueriesEXT(pair?2:1,queries);
    p_glGetIntegerv(GL_GPU_DISJOINT_EXT,&disjoint_before);
    GLint64 state_before = 0, state_after = 0;
    p_glGetInteger64v(GL_TIMESTAMP_EXT,&state_before);
    gl_ok("pre-query");
    double host_start = monotonic();
    if(timed) {
        if(pair) p_glQueryCounterEXT(queries[0],GL_TIMESTAMP_EXT);
        else p_glBeginQueryEXT(GL_TIME_ELAPSED_EXT,queries[0]);
    }
    int dispatch = strcmp(mode,"control") && strcmp(mode,"empty") && strcmp(mode,"empty-pair");
    printf("dispatch_count=%d\n",dispatch);
    if(dispatch) p_glDispatchCompute(groups,1,1);
    p_glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT | GL_BUFFER_UPDATE_BARRIER_BIT);
    if(timed) {
        if(pair) p_glQueryCounterEXT(queries[1],GL_TIMESTAMP_EXT);
        else p_glEndQueryEXT(GL_TIME_ELAPSED_EXT);
    }
    gl_ok("dispatch-query");
    GLsync fence = p_glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    gl_ok("fence-create");
    if (!fence) fail("fence-null");
    double start = monotonic(), deadline = start + 2.0;
    GLenum status = GL_TIMEOUT_EXPIRED;
    unsigned waits = 0;
    while (monotonic() < deadline && waits < 40) {
        status = p_glClientWaitSync(fence, GL_SYNC_FLUSH_COMMANDS_BIT, 50000000ull);
        ++waits;
        printf("fence_wait=%u status=0x%x elapsed_s=%.6f\n", waits, status, monotonic()-start);
        gl_ok("fence-wait");
        if (status == GL_ALREADY_SIGNALED || status == GL_CONDITION_SATISFIED) break;
        if (status != GL_TIMEOUT_EXPIRED) fail("fence-wait-failed");
    }
    if (status != GL_ALREADY_SIGNALED && status != GL_CONDITION_SATISFIED) fail("fence-deadline");
    double host_fence = monotonic();
    GLuint available[2] = {0,0};
    GLuint64 values[2] = {0,0};
    unsigned polls = 0;
    if(timed) {
        p_glFlush();
        double availability_deadline = monotonic()+2.0;
        for(unsigned q=0;q<(pair?2u:1u);++q) {
            while(!available[q] && monotonic()<availability_deadline && polls<4000) {
                p_glGetQueryObjectuivEXT(queries[q],GL_QUERY_RESULT_AVAILABLE_EXT,&available[q]);
                ++polls; gl_ok("query-availability");
                if(!available[q]) { struct timespec pause={0,1000000}; nanosleep(&pause,NULL); }
            }
            printf("query=%u available=%u polls=%u\n",q,available[q],polls);
            if(!available[q]) fail("query-availability-deadline");
            p_glGetQueryObjectui64vEXT(queries[q],GL_QUERY_RESULT_EXT,&values[q]);
            gl_ok("query-result64");
        }
    }
    GLint disjoint_after = -1;
    p_glGetIntegerv(GL_GPU_DISJOINT_EXT,&disjoint_after);
    p_glGetInteger64v(GL_TIMESTAMP_EXT,&state_after);
    gl_ok("post-query");
    double host_queries = monotonic();
    readback(buffers[0],words,"output.bin");
    readback(buffers[1],16,"control-output.bin");
    readback(buffers[2],64,"seeds-output.bin");
    double host_readback = monotonic();
    FILE *record = fopen("timing.json","w");
    if(!record) fail("timing-open");
    fprintf(record,"{\"mode\":\"%s\",\"repeats\":%u,\"elapsed_bits\":%d,\"timestamp_bits\":%d,"
        "\"raw_u64\":[%" PRIu64 ",%" PRIu64 "],\"available\":[%u,%u],\"disjoint_before\":%d,\"disjoint_after\":%d,"
        "\"state_timestamp_i64\":[%" PRId64 ",%" PRId64 "],\"host_monotonic_s\":[%.9f,%.9f,%.9f,%.9f],\"polls\":%u}\n",
        mode,repeats,elapsed_bits,timestamp_bits,(uint64_t)values[0],(uint64_t)values[1],available[0],available[1],
        disjoint_before,disjoint_after,(int64_t)state_before,(int64_t)state_after,host_start,host_fence,host_queries,host_readback,polls);
    if(fclose(record)) fail("timing-close");
    if(timed) p_glDeleteQueriesEXT(pair?2:1,queries);
    p_glDeleteSync(fence); p_glDeleteBuffers(3, buffers);
    p_glDeleteProgram(program); p_glDeleteShader(shader); gl_ok("GL-cleanup");
    egl_ok(p_eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT), "release-current");
    egl_ok(p_eglDestroyContext(display, context), "destroy-context");
    egl_ok(p_eglTerminate(display), "terminate"); dlclose(egl);
    puts("READBACK_COMPLETE (host oracle is performed by run_gles_time.py)");
    return 0;
}
