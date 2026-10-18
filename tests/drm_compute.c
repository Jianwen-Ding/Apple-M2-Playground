/* Direct Asahi DRM compute submission: no Mesa, no Vulkan.
 *
 * Builds everything a compute dispatch needs by hand: VM, BOs, USC pipeline
 * words, CDM control stream, one DRM_ASAHI_CMD_COMPUTE with start/end
 * firmware timestamps. The shader is raw AGX main code read from a file; it
 * receives u4 = 0 (index offset), u5 = count, u6_u7 = output VA, matching
 * the main of the pinned Vulkan control, and runs with no preshader.
 *
 * Output buffer layout matches tests/vulkan_compute.c (8 guards, rounded
 * payload, 8 guards, 16 patterned tail words) so oracles carry over.
 *
 * Optional table file: copied to data BO offset 1 MiB, its VA passed in u8_u9
 * (pointer-chase / load probes). The control main never reads u8 onward.
 *
 * Probe overrides (environment, all optional; defaults reproduce the base layout):
 *   AGX_USC_WORDS_OFF, AGX_CODE_OFF   USC offsets (64 B aligned, < 0x10000)
 *   AGX_CDM_OFF                       CDM stream offset in the data BO (< 0x8000, 8 B aligned)
 *   AGX_LOCAL_X/Y/Z                   CDM local size (global X stays the rounded count)
 *   AGX_GLOBAL_X                      CDM global size in X (threads; default the rounded count)
 *   AGX_GLOBAL_Y/Z                    CDM global size in Y/Z (threads; default 1)
 *   AGX_UNIFORM_GROUPS                CDM launch word 0 uniform register count in groups of 64 halves (default 1, max 7)
 *   AGX_WORD0_OR                      bits ORed into CDM launch word 0
 *   AGX_HELPER_DATA, AGX_HELPER_CFG   drm_asahi_helper_program data/cfg ("table" = table VA)
 *   AGX_HELPER_CODE, AGX_HELPER_OFF   helper program file at USC offset AGX_HELPER_OFF (default 0x4000); binary = offset | 1
 *   AGX_SAMPLER_COUNT                 sampler_count with sampler_heap = zeroed data page at +0x6000
 *   AGX_CMDS, AGX_CMD_BARRIER         N (1-64) compute commands per SUBMIT; barrier "chain" (default) or "none"
 *   AGX_QUEUES                        N (2-32) queues each submit the command once per repeat (concurrency test)
 *   AGX_CLEAN_EXIT                    default 1 = munmap + GEM_CLOSE at exit (0 leaks every BO in the kernel), 2 = also unbind
 *   AGX_SYNC_MODE                     0|1|2 two-queue ordering test: B no wait / waits binary syncobj / timeline point
 *   AGX_PRIORITY                      queue priority (0 low, 1 medium)
 *   AGX_USC_ORDER                     order of USC pipeline words (default "ushrn")
 *   AGX_PRESHADER                     1 = Preshader word (preamble at usc_words + 0x200) instead of No preshader
 *   AGX_PRESHADER_CODE                preamble file for AGX_PRESHADER (default: a single `stop`)
 *   AGX_SHARED_WORD                   full 32-bit USC Shared word (tag 0x4d must be kept by the caller)
 *   AGX_SHADER_UNK2                   USC Shader word unk_2 field (default 3, Mesa's compute value)
 *   AGX_TABLE_OUT                     write the table region back to this path after the last submit
 *   AGX_CPU_CLOCK                     word index in the table: a CPU thread keeps writing, while the
 *                                     submits run, word[i] = spin counter and word[i+1] = low 32 bits
 *                                     of CNTVCT_EL0 (the ARM generic timer). Calibration is printed.
 *   AGX_CPU_CLOCK_FLUSH               1 = clean each write to the point of coherency (dc cvac)
 *   AGX_CPU_ECHO, AGX_CPU_ECHO_OUT     T,E,C words: CPU thread echoes token word T into E and writes CNTVCT to C (safe-03 step 4)
 *   AGX_CPU_CLOCK_LINES               write the pair to this many copies, 32 words (128 B) apart (default 1)
 *
 * usage: drm_compute node code.bin count readback repeats [gprs [table.bin]]
 * Bounded: count <= 2^24, grid <= 2^30 threads, repeats <= 64, table <= 512 MiB, 3 s wait per submit.
 * The table goes at 1 MiB, or after the output when the output is larger. */
#define _POSIX_C_SOURCE 200809L
#include <drm/drm.h>
#include <drm/asahi_drm.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>
#include <stdatomic.h>

static int fd = -1;
static void require(int ok, const char *stage)
{
    if (!ok) { printf("{\"failure\":\"%s\",\"errno\":%d}\n", stage, errno); exit(1); }
}
static void io(unsigned long request, void *arg, const char *stage)
{
    int r; do r = ioctl(fd, request, arg); while (r < 0 && (errno == EINTR || errno == EAGAIN));
    require(r == 0, stage);
}
static uint64_t now_ns(void)
{
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
}

struct bo { uint32_t handle; uint64_t size, va; uint8_t *map; };

static struct bo bo_create(uint64_t size, uint32_t vm, uint64_t va, uint32_t bind_flags)
{
    struct bo b = {.size = size, .va = va};
    struct drm_asahi_gem_create gc = {.size = size, .flags = DRM_ASAHI_GEM_WRITEBACK};
    io(DRM_IOCTL_ASAHI_GEM_CREATE, &gc, "gem-create");
    b.handle = gc.handle;
    struct drm_asahi_gem_mmap_offset mo = {.handle = b.handle};
    io(DRM_IOCTL_ASAHI_GEM_MMAP_OFFSET, &mo, "gem-mmap-offset");
    b.map = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)mo.offset);
    require(b.map != MAP_FAILED, "mmap");
    memset(b.map, 0, size);
    if (va) {
        struct drm_asahi_gem_bind_op op = {.flags = bind_flags, .handle = b.handle, .range = size, .addr = va};
        struct drm_asahi_vm_bind vb = {.vm_id = vm, .num_binds = 1, .stride = sizeof op, .userptr = (uint64_t)(uintptr_t)&op};
        io(DRM_IOCTL_ASAHI_VM_BIND, &vb, "vm-bind");
    }
    return b;
}

static void put32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
static uint64_t env(const char *name, uint64_t fallback)
{
    const char *v = getenv(name); if (!v || !*v) return fallback;
    char *end; uint64_t x = strtoull(v, &end, 0); require(*end == 0, name); return x;
}
static void put64(uint8_t *p, uint64_t v) { memcpy(p, &v, 8); }

static volatile uint32_t *clock_words;
static atomic_int clock_run, clock_flush, clock_lines = 1;
static uint64_t clock_iters, clock_t0, clock_t1;
static inline uint64_t cntvct(void) { uint64_t v; __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(v)); return v; }
static void *clock_thread(void *arg)
{
    (void)arg;
    uint32_t n = 0;
    clock_t0 = cntvct();
    while (atomic_load_explicit(&clock_run, memory_order_relaxed)) {
        ++n;
        for (int l = 0; l < clock_lines; l++) {
            volatile uint32_t *w = clock_words + 32 * l;
            w[0] = n; w[1] = (uint32_t)cntvct();
            if (clock_flush) __asm__ volatile("dc cvac, %0" :: "r"(w) : "memory");
        }
    }
    clock_t1 = cntvct(); clock_iters = n;
    return NULL;
}

/* AGX_CPU_ECHO=T,E,C (table word indices; simulator task safe-03 step 4): a CPU thread polls word T (a token the
   shader stores); on every new value it records (token, CNTVCT when first seen), then writes word E = token. It
   keeps writing word C = low 32 bits of CNTVCT on every poll. Observations go to AGX_CPU_ECHO_OUT (binary pairs of
   uint64). The thread never waits on the GPU: it only reacts to what it sees, until the submits are done. */
static volatile uint32_t *echo_t, *echo_e, *echo_c;
static atomic_int echo_run;
static uint64_t echo_log[2 * 65536];
static uint32_t echo_n;
static void *echo_thread(void *arg)
{
    (void)arg;
    uint32_t last = echo_t[0];
    while (atomic_load_explicit(&echo_run, memory_order_relaxed)) {
        uint32_t t = echo_t[0];
        uint64_t now = cntvct();
        if (t != last) {
            if (echo_n < 65536) { echo_log[2 * echo_n] = t; echo_log[2 * echo_n + 1] = now; echo_n++; }
            echo_e[0] = t; last = t;
        }
        echo_c[0] = (uint32_t)now;
    }
    return NULL;
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    require(argc >= 6 && argc <= 8, "usage: node code.bin count readback repeats [gprs [table.bin]]");
    char *end;
    unsigned long count = strtoul(argv[3], &end, 10); require(*end == 0 && count >= 1 && count <= (1ul << 24), "count");
    unsigned long reps = strtoul(argv[5], &end, 10); require(*end == 0 && reps >= 1 && reps <= 64, "repeats");
    unsigned long gprs = argc >= 7 ? strtoul(argv[6], &end, 10) : 8;
    require(gprs >= 8 && gprs <= 256, "gprs");

    FILE *f = fopen(argv[2], "rb"); require(f != NULL, "code-open");
    static uint8_t code[1 << 20]; size_t code_size = fread(code, 1, sizeof code, f);
    require(code_size > 0 && code_size < sizeof code - 64 && feof(f), "code-read"); fclose(f);

    fd = open(argv[1], O_RDWR | O_CLOEXEC); require(fd >= 0, "open");
    struct drm_asahi_params_global p = {0};
    struct drm_asahi_get_params gp = {.param_group = 0, .pointer = (uint64_t)(uintptr_t)&p, .size = sizeof p};
    io(DRM_IOCTL_ASAHI_GET_PARAMS, &gp, "get-params");
    int g14x = p.gpu_generation >= 14 && p.num_clusters_total > 1;
    printf("{\"params\":{\"gen\":%u,\"variant\":\"%c\",\"rev\":%u,\"clusters\":%u,\"vm_start\":%" PRIu64 ",\"vm_end\":%" PRIu64
           ",\"kernel_min\":%" PRIu64 ",\"ts_hz\":%" PRIu64 ",\"max_khz\":%u,\"features\":%" PRIu64 ",\"g14x\":%d}}\n",
           p.gpu_generation, (char)p.gpu_variant, p.gpu_revision, p.num_clusters_total, (uint64_t)p.vm_start,
           (uint64_t)p.vm_end, (uint64_t)p.vm_kernel_min_size, (uint64_t)p.command_timestamp_frequency_hz,
           p.max_frequency_khz, (uint64_t)p.features, g14x);

    /* Mesa's layout: USC heap at the 4 GiB-aligned bottom above 2^36, data after it, kernel range on top. */
    uint64_t shader_base = (p.vm_start > (1ull << 36) ? p.vm_start : (1ull << 36));
    shader_base = (shader_base + 0xffffffffull) & ~0xffffffffull;
    uint64_t data_base = shader_base + 0x100000000ull;
    uint64_t ksize = p.vm_kernel_min_size > (32ull << 30) ? p.vm_kernel_min_size : (32ull << 30);
    struct drm_asahi_vm_create vc = {.kernel_start = p.vm_end - ksize, .kernel_end = p.vm_end};
    require(data_base + (1ull << 30) < vc.kernel_start, "address-layout");
    io(DRM_IOCTL_ASAHI_VM_CREATE, &vc, "vm-create");

    const uint64_t page = 16384;
    const uint32_t usc_words = (uint32_t)env("AGX_USC_WORDS_OFF", 0x1000), code_off = (uint32_t)env("AGX_CODE_OFF", 0x2000);
    const uint32_t cdm_off = (uint32_t)env("AGX_CDM_OFF", 0x4000);
    require(usc_words % 64 == 0 && code_off % 64 == 0 && usc_words < 0x10000 && code_off < 0x10000 &&
            (code_off >= usc_words + 64 || code_off + code_size + 64 <= usc_words), "usc-offsets");
    require(cdm_off % 8 == 0 && cdm_off >= 0x100 && cdm_off + 0x100 <= 0x6000, "cdm-offset");
    uint64_t usc_end = (usc_words + 64 > code_off + code_size + 64) ? usc_words + 64 : code_off + code_size + 64;
    /* Optional helper program at AGX_HELPER_OFF (default 0x4000), after the main code. */
    static uint8_t helper_code[0x10000]; size_t helper_size = 0;
    const uint32_t helper_off = (uint32_t)env("AGX_HELPER_OFF", 0x4000);
    const char *hc = getenv("AGX_HELPER_CODE");
    if (hc && *hc) {
        FILE *hf = fopen(hc, "rb"); require(hf != NULL, "helper-code-open");
        helper_size = fread(helper_code, 1, sizeof helper_code, hf); require(helper_size > 0 && helper_size < sizeof helper_code && feof(hf), "helper-code-read"); fclose(hf);
        require(helper_off % 64 == 0 && helper_off >= code_off + code_size + 64 && helper_off >= usc_words + 0x400, "helper-placement");
        if (helper_off + helper_size + 64 > usc_end) usc_end = helper_off + helper_size + 64;
    }
    uint64_t usc_size = (usc_end + page - 1) & ~(page - 1);
    uint32_t rounded = (uint32_t)((count + 31) / 32 * 32), words = 8 + rounded + 8 + 16;
    /* Output at 0x8000; table at 1 MiB, or after the output when the output reaches past 1 MiB. */
    const uint64_t table_off = (0x8000 + (uint64_t)words * 4 + page - 1 > (1u << 20)) ? (0x8000 + (uint64_t)words * 4 + page - 1) & ~(page - 1) : (1u << 20);
    uint64_t table_size = 0;
    FILE *tf = NULL;
    if (argc == 8) {
        tf = fopen(argv[7], "rb"); require(tf != NULL, "table-open");
        require(fseek(tf, 0, SEEK_END) == 0, "table-seek"); long tn = ftell(tf); rewind(tf);
        require(tn > 0 && tn <= (512l << 20) && tn % 4 == 0, "table-size"); table_size = (uint64_t)tn;
    }
    require(0x8000 + (uint64_t)words * 4 <= table_off, "output-fits-below-table");
    uint64_t data_size = ((table_size ? table_off + table_size : 0x8000 + (uint64_t)words * 4) + page - 1) & ~(page - 1);
    struct bo usc = bo_create(usc_size, vc.vm_id, shader_base, DRM_ASAHI_BIND_READ);
    struct bo data = bo_create(data_size, vc.vm_id, data_base, DRM_ASAHI_BIND_READ | DRM_ASAHI_BIND_WRITE);
    struct bo tsb = bo_create(page, vc.vm_id, 0, 0);
    struct drm_asahi_gem_bind_object bo_ts = {.op = DRM_ASAHI_BIND_OBJECT_OP_BIND, .flags = DRM_ASAHI_BIND_OBJECT_USAGE_TIMESTAMPS,
                                              .handle = tsb.handle, .range = page};
    io(DRM_IOCTL_ASAHI_GEM_BIND_OBJECT, &bo_ts, "bind-timestamps");

    if (tf) {
        require(fread(data.map + table_off, 1, table_size, tf) == table_size && fclose(tf) == 0, "table-read");
        printf("{\"table\":{\"bytes\":%" PRIu64 ",\"va\":%" PRIu64 "}}\n", table_size, data.va + table_off);
    }

    /* USC BO: pipeline words at 0x1000, code at 0x2000 (USC-relative = BO offset). */
    memcpy(usc.map + code_off, code, code_size);
    const uint64_t unif_va = data.va + 0x0, out_va = data.va + 0x8000, cdm_va = data.va + cdm_off;
    uint8_t *w = usc.map + usc_words;
    /* Pipeline words are emitted in AGX_USC_ORDER (default "ushrn"): u = Uniform, s = Shared,
       h = Shader, r = Registers, n = No preshader (or a Preshader word when AGX_PRESHADER=1,
       pointing at a one-instruction `stop` preamble placed at usc_words + 0x200). */
    const char *order = getenv("AGX_USC_ORDER"); if (!order || !*order) order = "ushrn";
    int preshader = (int)env("AGX_PRESHADER", 0);
    require(strlen(order) == 5 && strchr(order, 'u') && strchr(order, 's') && strchr(order, 'h') && strchr(order, 'r') && strchr(order, 'n'), "usc-order");
    const uint32_t pre_off = usc_words + 0x200;
    if (preshader) {
        /* Preamble: AGX_PRESHADER_CODE file if given, else a single `stop`. */
        static uint8_t pre[0x2000]; size_t pre_size = 2; pre[0] = 0x88; pre[1] = 0x00;
        const char *pc = getenv("AGX_PRESHADER_CODE");
        if (pc && *pc) {
            FILE *pf = fopen(pc, "rb"); require(pf != NULL, "preshader-code-open");
            pre_size = fread(pre, 1, sizeof pre, pf); require(pre_size > 0 && pre_size < sizeof pre && feof(pf), "preshader-code-read"); fclose(pf);
        }
        require(pre_off + pre_size + 64 <= usc_size && (pre_off + pre_size + 64 <= code_off || pre_off >= code_off + code_size + 64) &&
                pre_off + pre_size + 64 <= (usc_words > pre_off ? usc_words : usc_size), "preshader-placement");
        memcpy(usc.map + pre_off, pre, pre_size);
    }
    uint32_t helper_binary = 0;
    if (helper_size) {
        memcpy(usc.map + helper_off, helper_code, helper_size);
        helper_binary = helper_off | 1;   /* tagged USC pointer, as Mesa's agx_helper_program() */
        printf("{\"helper\":{\"bytes\":%zu,\"binary\":%u}}\n", helper_size, helper_binary);
    }
    for (const char *o = order; *o; o++) {
        if (*o == 'u') {
            /* USC Uniform: tag 0x1d, start halfs 8 (u4), size 12 halfs (u4..u9), buffer >> 2 at bit 26. */
            put64(w, 0x1dull | (8ull << 8) | (12ull << 20) | ((unif_va >> 2) << 26)); w += 8;
        } else if (*o == 's') {
            /* USC Shared, none: tag 0x4d, layout vertex/compute 0x24 at bit 10, bytes 65536 -> groups(256) of 8 bits = 0 ("all"). */
            put32(w, (uint32_t)env("AGX_SHARED_WORD", 0x4du | (0x24u << 10))); w += 4;
        } else if (*o == 'h') {
            /* USC Shader: tag 0x0d, unk_2 = 3 at bit 10 (compute), code address at bit 16 (6 bytes). */
            uint64_t sh = 0x0dull | ((env("AGX_SHADER_UNK2", 3) & 63) << 10) | ((uint64_t)code_off << 16); memcpy(w, &sh, 6); w += 6;
        } else if (*o == 'r') {
            /* USC Registers: tag 0x8d, register count groups(8) at bit 8 (5 bits, 0 = 256), unk_4 = 1 at bit 24. */
            uint32_t rc = (uint32_t)((gprs + 7) / 8) & 31; put32(w, 0x8du | (rc << 8) | (1u << 24)); w += 4;
        } else if (*o == 'n' && !preshader) {
            /* USC No preshader: tag 0x88 (2 bytes). */
            w[0] = 0x88; w[1] = 0; w += 2;
        } else if (*o == 'n') {
            /* USC Preshader: tag 0x38, unk 0xc08000 (Mesa's exact value), code address at bit 32. */
            put32(w, 0x38u | (0xc08000u << 8)); put32(w + 4, pre_off); w += 8;
        } else require(0, "usc-order-letter");
    }
    printf("{\"usc_words_hex\":\"");
    for (uint8_t *q = usc.map + usc_words; q < w; q++) printf("%02x", *q);
    printf("\"}\n");

    /* Uniforms u4 = 0, u5 = count, u6_u7 = output VA, u8_u9 = table VA (0 without a table). */
    put32(data.map + 0, 0); put32(data.map + 4, (uint32_t)count); put64(data.map + 8, out_va);
    put64(data.map + 16, table_size ? data.va + table_off : 0);

    /* CDM control stream. */
    uint8_t *c = data.map + cdm_off;
    const uint32_t ugroups = (uint32_t)env("AGX_UNIFORM_GROUPS", 1);   /* CDM Launch word 0 `Uniform register count`, groups of 64 halves, 3 bits */
    require(ugroups <= 7, "uniform-groups");
    put32(c, (ugroups << 1) | (uint32_t)env("AGX_WORD0_OR", 0)); c += 4;                /* Launch word 0: uniform count groups(64) (default 1); direct; block type 0 */
    put32(c, usc_words); c += 4;               /* Launch word 1: pipeline (64 B aligned, USC relative) */
    if (g14x) { put32(c, 0); put32(c + 4, 1u << 30); c += 8; }
    uint32_t gx = (uint32_t)env("AGX_GLOBAL_X", rounded), gy = (uint32_t)env("AGX_GLOBAL_Y", 1), gz = (uint32_t)env("AGX_GLOBAL_Z", 1);
    uint32_t lx = (uint32_t)env("AGX_LOCAL_X", 32), ly = (uint32_t)env("AGX_LOCAL_Y", 1), lz = (uint32_t)env("AGX_LOCAL_Z", 1);
    require(lx >= 1 && ly >= 1 && lz >= 1 && lx * ly * lz <= 1024 && gx >= 1 && gx % lx == 0 && gy % ly == 0 && gz % lz == 0 &&
            (uint64_t)gx * gy * gz <= (1ull << 30), "grid/local size");
    put32(c, gx); put32(c + 4, gy); put32(c + 8, gz); c += 12;  /* global size in threads */
    put32(c, lx); put32(c + 4, ly); put32(c + 8, lz); c += 12;     /* local size */
    put32(c, (3u << 29) | 0xfffffu); c += 4;   /* Barrier: Mesa's unk0..19 incl. USC cache invalidate */
    put32(c, 2u << 29); put32(c + 4, 0); c += 8;  /* Stream terminate */
    uint64_t cdm_end = cdm_va + (uint64_t)(c - (data.map + cdm_off));
    printf("{\"cdm_hex\":\"");
    for (uint8_t *q = data.map + cdm_off; q < c; q++) printf("%02x", *q);
    printf("\"}\n");

    struct drm_asahi_queue_create qc = {.vm_id = vc.vm_id, .priority = (uint32_t)env("AGX_PRIORITY", DRM_ASAHI_PRIORITY_MEDIUM), .usc_exec_base = shader_base};
    io(DRM_IOCTL_ASAHI_QUEUE_CREATE, &qc, "queue-create");
    struct drm_syncobj_create sc = {0};
    io(DRM_IOCTL_SYNCOBJ_CREATE, &sc, "syncobj-create");

    uint32_t *out = (uint32_t *)(data.map + 0x8000);
    pthread_t clock_tid;
    const char *cw = getenv("AGX_CPU_CLOCK");
    if (cw && *cw) {
        unsigned long wi = strtoul(cw, NULL, 0);
        atomic_store(&clock_lines, (int)env("AGX_CPU_CLOCK_LINES", 1));
        require(clock_lines >= 1 && clock_lines <= 64 && table_size > 0 && (wi + 32 * (uint64_t)clock_lines) * 4 <= table_size, "cpu-clock-word");
        clock_words = (volatile uint32_t *)(data.map + table_off) + wi;
        atomic_store(&clock_flush, (int)env("AGX_CPU_CLOCK_FLUSH", 0));
        atomic_store(&clock_run, 1);
        require(pthread_create(&clock_tid, NULL, clock_thread, NULL) == 0, "cpu-clock-thread");
        while (clock_words[0] == 0) ;   /* running before the first submit */
    }
    pthread_t echo_tid;
    const char *ce = getenv("AGX_CPU_ECHO");
    if (ce && *ce) {
        unsigned long ti, ei, ci; require(sscanf(ce, "%lu,%lu,%lu", &ti, &ei, &ci) == 3, "cpu-echo-syntax");
        require(table_size > 0 && ti * 4 < table_size && ei * 4 < table_size && ci * 4 < table_size, "cpu-echo-words");
        uint32_t *tw = (uint32_t *)(data.map + table_off);
        echo_t = tw + ti; echo_e = tw + ei; echo_c = tw + ci;
        atomic_store(&echo_run, 1);
        require(pthread_create(&echo_tid, NULL, echo_thread, NULL) == 0, "cpu-echo-thread");
        while (echo_c[0] == 0) ;          /* running before the first submit */
    }
    /* AGX_QUEUES=N (2-32): N queues on this VM each submit the same command once per repeat, no dependencies; all are
       waited for, and the firmware start / end of each is printed (simulator task safe-04 step 2). */
    const unsigned nq = (unsigned)env("AGX_QUEUES", 0);
    if (nq) {
        require(nq >= 2 && nq <= 32 && 16 * nq <= page, "queues");
        uint32_t qid[32], sh[32];
        for (unsigned k = 0; k < nq; k++) {
            struct drm_asahi_queue_create qk = {.vm_id = vc.vm_id, .priority = qc.priority, .usc_exec_base = shader_base};
            io(DRM_IOCTL_ASAHI_QUEUE_CREATE, &qk, "queue-create-n"); qid[k] = qk.queue_id;
            struct drm_syncobj_create sk = {0}; io(DRM_IOCTL_SYNCOBJ_CREATE, &sk, "syncobj-create-n"); sh[k] = sk.handle;
        }
        for (unsigned long rep = 0; rep < reps; rep++) {
            for (uint32_t j = 0; j < words; j++) out[j] = j < words - 16 ? 0xcdcdcdcdu : 0xa5a50000u + j - (words - 16);
            memset(tsb.map, 0, 16 * nq);
            static struct { struct drm_asahi_cmd_header h; struct drm_asahi_cmd_compute c; } qcmd[32];
            uint64_t hs[33]; hs[0] = now_ns();
            for (unsigned k = 0; k < nq; k++) {
                memset(&qcmd[k], 0, sizeof qcmd[k]);
                qcmd[k].h.cmd_type = DRM_ASAHI_CMD_COMPUTE; qcmd[k].h.size = sizeof(struct drm_asahi_cmd_compute);
                qcmd[k].h.vdm_barrier = DRM_ASAHI_BARRIER_NONE; qcmd[k].h.cdm_barrier = 0;
                qcmd[k].c.cdm_ctrl_stream_base = cdm_va; qcmd[k].c.cdm_ctrl_stream_end = cdm_end;
                qcmd[k].c.ts.start.handle = bo_ts.object_handle; qcmd[k].c.ts.start.offset = 16 * k;
                qcmd[k].c.ts.end.handle = bo_ts.object_handle; qcmd[k].c.ts.end.offset = 16 * k + 8;
                struct drm_asahi_sync os = {.sync_type = DRM_ASAHI_SYNC_SYNCOBJ, .handle = sh[k]};
                struct drm_asahi_submit sk = {.syncs = (uint64_t)(uintptr_t)&os, .cmdbuf = (uint64_t)(uintptr_t)&qcmd[k],
                                              .queue_id = qid[k], .out_sync_count = 1, .cmdbuf_size = sizeof qcmd[k]};
                io(DRM_IOCTL_ASAHI_SUBMIT, &sk, "submit-n"); hs[k + 1] = now_ns();
            }
            struct drm_syncobj_wait sw = {.handles = (uint64_t)(uintptr_t)sh, .count_handles = nq, .flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL,
                                          .timeout_nsec = (int64_t)(hs[0] + 3000000000ull)};
            int r = ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &sw); int werr = r ? errno : 0;
            printf("{\"multi\":%lu,\"queues\":%u,\"wait\":%d,\"errno\":%d,\"submit_ns\":%" PRIu64 ",\"ts\":[", rep, nq, r, werr, hs[nq] - hs[0]);
            for (unsigned k = 0; k < nq; k++) { uint64_t tk[2]; memcpy(tk, tsb.map + 16 * k, 16); printf("%s[%" PRIu64 ",%" PRIu64 "]", k ? "," : "", tk[0], tk[1]); }
            printf("]}\n");
            require(r == 0, "syncobj-wait-n");
            struct drm_syncobj_array reset = {.handles = (uint64_t)(uintptr_t)sh, .count_handles = nq};
            io(DRM_IOCTL_SYNCOBJ_RESET, &reset, "syncobj-reset-n");
        }
        for (unsigned k = 0; k < nq; k++) { struct drm_asahi_queue_destroy qd = {.queue_id = qid[k]}; io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &qd, "queue-destroy-n"); }
        reps = 0;
    }
    /* AGX_SYNC_MODE=0|1|2: two-queue ordering test (simulator task safe-12 step 4). Each repeat submits the same
       command on queue A, then on a second queue B: 0 = B has no wait, 1 = B waits on A's binary syncobj,
       2 = B waits on timeline point rep+1 that A signals. Both are waited for; firmware timestamps of both are printed. */
    const char *sm = getenv("AGX_SYNC_MODE");
    if (sm && *sm) {
        int mode = (int)strtol(sm, NULL, 0); require(mode >= 0 && mode <= 2, "sync-mode");
        struct drm_asahi_queue_create qb = {.vm_id = vc.vm_id, .priority = qc.priority, .usc_exec_base = shader_base};
        io(DRM_IOCTL_ASAHI_QUEUE_CREATE, &qb, "queue-create-b");
        struct drm_syncobj_create sb = {0}, tl = {0};
        io(DRM_IOCTL_SYNCOBJ_CREATE, &sb, "syncobj-create-b"); io(DRM_IOCTL_SYNCOBJ_CREATE, &tl, "syncobj-create-tl");
        for (unsigned long rep = 0; rep < reps; rep++) {
            for (uint32_t j = 0; j < words; j++) out[j] = j < words - 16 ? 0xcdcdcdcdu : 0xa5a50000u + j - (words - 16);
            memset(tsb.map, 0, 32);
            struct { struct drm_asahi_cmd_header h; struct drm_asahi_cmd_compute c; } cmd[2];
            for (int k = 0; k < 2; k++) {
                memset(&cmd[k], 0, sizeof cmd[k]);
                cmd[k].h.cmd_type = DRM_ASAHI_CMD_COMPUTE; cmd[k].h.size = sizeof(struct drm_asahi_cmd_compute);
                cmd[k].h.vdm_barrier = DRM_ASAHI_BARRIER_NONE; cmd[k].h.cdm_barrier = 0;
                cmd[k].c.cdm_ctrl_stream_base = cdm_va; cmd[k].c.cdm_ctrl_stream_end = cdm_end;
                cmd[k].c.ts.start.handle = bo_ts.object_handle; cmd[k].c.ts.start.offset = 16 * k;
                cmd[k].c.ts.end.handle = bo_ts.object_handle; cmd[k].c.ts.end.offset = 16 * k + 8;
            }
            struct drm_asahi_sync sa[2] = {{.sync_type = DRM_ASAHI_SYNC_SYNCOBJ, .handle = sc.handle},
                                           {.sync_type = DRM_ASAHI_SYNC_TIMELINE_SYNCOBJ, .handle = tl.handle, .timeline_value = rep + 1}};
            struct drm_asahi_submit suba = {.syncs = (uint64_t)(uintptr_t)sa, .cmdbuf = (uint64_t)(uintptr_t)&cmd[0],
                                            .queue_id = qc.queue_id, .out_sync_count = mode == 2 ? 2 : 1, .cmdbuf_size = sizeof cmd[0]};
            struct drm_asahi_sync sbs[2] = {{.sync_type = mode == 2 ? DRM_ASAHI_SYNC_TIMELINE_SYNCOBJ : DRM_ASAHI_SYNC_SYNCOBJ,
                                             .handle = mode == 2 ? tl.handle : sc.handle, .timeline_value = mode == 2 ? rep + 1 : 0},
                                            {.sync_type = DRM_ASAHI_SYNC_SYNCOBJ, .handle = sb.handle}};
            struct drm_asahi_submit subb = {.syncs = (uint64_t)(uintptr_t)(mode ? &sbs[0] : &sbs[1]), .cmdbuf = (uint64_t)(uintptr_t)&cmd[1],
                                            .queue_id = qb.queue_id, .in_sync_count = mode ? 1 : 0, .out_sync_count = 1, .cmdbuf_size = sizeof cmd[1]};
            uint64_t h0 = now_ns();
            io(DRM_IOCTL_ASAHI_SUBMIT, &suba, "submit-a");
            uint64_t h1 = now_ns();
            io(DRM_IOCTL_ASAHI_SUBMIT, &subb, "submit-b");
            uint64_t h2 = now_ns();
            uint32_t hs[2] = {sc.handle, sb.handle};
            struct drm_syncobj_wait sw = {.handles = (uint64_t)(uintptr_t)hs, .count_handles = 2, .flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL,
                                          .timeout_nsec = (int64_t)(h0 + 3000000000ull)};
            int r = ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &sw); int werr = r ? errno : 0;
            uint64_t h3 = now_ns();
            uint64_t ts[4]; memcpy(ts, tsb.map, 32);
            printf("{\"pair\":%lu,\"mode\":%d,\"wait\":%d,\"errno\":%d,\"a\":[%" PRIu64 ",%" PRIu64 "],\"b\":[%" PRIu64 ",%" PRIu64 "],"
                   "\"host_submit_ns\":[%" PRIu64 ",%" PRIu64 "],\"host_total_ns\":%" PRIu64 "}\n",
                   rep, mode, r, werr, ts[0], ts[1], ts[2], ts[3], h1 - h0, h2 - h1, h3 - h0);
            require(r == 0, "syncobj-wait-pair");
            struct drm_syncobj_array reset = {.handles = (uint64_t)(uintptr_t)hs, .count_handles = 2};
            io(DRM_IOCTL_SYNCOBJ_RESET, &reset, "syncobj-reset-pair");
        }
        struct drm_asahi_queue_destroy qdb = {.queue_id = qb.queue_id};
        io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &qdb, "queue-destroy-b");
        reps = 0;   /* skip the single-queue loop; readback and cleanup follow */
    }
    for (unsigned long rep = 0; rep < reps; rep++) {
        for (uint32_t j = 0; j < words; j++) out[j] = j < words - 16 ? 0xcdcdcdcdu : 0xa5a50000u + j - (words - 16);
        /* AGX_CMDS=N (1-64): N compute commands in this one SUBMIT, command k timestamped at 16k / 16k+8.
           AGX_CMD_BARRIER: "chain" (default; command k waits on the k commands before it in this submit) or
           "none" (commands after the first wait on nothing). */
        static struct { struct drm_asahi_cmd_header h; struct drm_asahi_cmd_compute c; } cmd[64];
        const unsigned ncmd = (unsigned)env("AGX_CMDS", 1);
        require(ncmd >= 1 && ncmd <= 64 && ncmd <= p.max_commands_per_submission, "cmds");
        const char *cb = getenv("AGX_CMD_BARRIER"); int chain = !(cb && !strcmp(cb, "none"));
        require(!cb || !*cb || !strcmp(cb, "none") || !strcmp(cb, "chain"), "cmd-barrier");
        memset(tsb.map, 0, 16 * ncmd);
        for (unsigned k = 0; k < ncmd; k++) {
            memset(&cmd[k], 0, sizeof cmd[k]);
            cmd[k].h.cmd_type = DRM_ASAHI_CMD_COMPUTE; cmd[k].h.size = sizeof(struct drm_asahi_cmd_compute);
            cmd[k].h.vdm_barrier = DRM_ASAHI_BARRIER_NONE;
            cmd[k].h.cdm_barrier = k == 0 ? 0 : (chain ? (uint16_t)k : DRM_ASAHI_BARRIER_NONE);
            cmd[k].c.cdm_ctrl_stream_base = cdm_va; cmd[k].c.cdm_ctrl_stream_end = cdm_end;
            cmd[k].c.ts.start.handle = bo_ts.object_handle; cmd[k].c.ts.start.offset = 16 * k;
            cmd[k].c.ts.end.handle = bo_ts.object_handle; cmd[k].c.ts.end.offset = 16 * k + 8;
            cmd[k].c.helper.binary = helper_binary; cmd[k].c.helper.cfg = (uint32_t)env("AGX_HELPER_CFG", 0);
            cmd[k].c.helper.data = (getenv("AGX_HELPER_DATA") && !strcmp(getenv("AGX_HELPER_DATA"), "table")) ? data.va + table_off : env("AGX_HELPER_DATA", 0);
            cmd[k].c.sampler_count = (uint32_t)env("AGX_SAMPLER_COUNT", 0);
            cmd[k].c.sampler_heap = env("AGX_SAMPLER_COUNT", 0) ? data.va + 0x6000 : 0;
        }
        struct drm_asahi_sync out_sync = {.sync_type = DRM_ASAHI_SYNC_SYNCOBJ, .handle = sc.handle};
        struct drm_asahi_submit sub = {.syncs = (uint64_t)(uintptr_t)&out_sync, .cmdbuf = (uint64_t)(uintptr_t)cmd,
                                       .queue_id = qc.queue_id, .out_sync_count = 1, .cmdbuf_size = (uint32_t)(sizeof cmd[0] * ncmd)};
        struct drm_asahi_get_time t0 = {0}, t1 = {0};
        io(DRM_IOCTL_ASAHI_GET_TIME, &t0, "get-time");
        uint64_t h0 = now_ns();
        io(DRM_IOCTL_ASAHI_SUBMIT, &sub, "submit");
        struct drm_syncobj_wait sw = {.handles = (uint64_t)(uintptr_t)&sc.handle, .count_handles = 1,
                                      .timeout_nsec = (int64_t)(h0 + 3000000000ull)};
        int r = ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &sw);
        uint64_t h1 = now_ns();
        io(DRM_IOCTL_ASAHI_GET_TIME, &t1, "get-time");
        uint64_t ts[2]; memcpy(ts, tsb.map, 16);
        printf("{\"rep\":%lu,\"wait\":%d,\"errno\":%d,\"host_ns\":%" PRIu64 ",\"fw_ts\":[%" PRIu64 ",%" PRIu64 "],\"drm_time\":[%" PRIu64 ",%" PRIu64 "]",
               rep, r, r ? errno : 0, h1 - h0, ts[0], ts[1], (uint64_t)t0.gpu_timestamp, (uint64_t)t1.gpu_timestamp);
        if (ncmd > 1) {
            printf(",\"cmd_ts\":[");
            for (unsigned k = 0; k < ncmd; k++) { uint64_t tk[2]; memcpy(tk, tsb.map + 16 * k, 16); printf("%s[%" PRIu64 ",%" PRIu64 "]", k ? "," : "", tk[0], tk[1]); }
            printf("]");
        }
        /* AGX_TABLE_PEEK=i,j,...: table words i, j, ... after this submission (e.g. counters a kernel accumulates) */
        const char *peek = getenv("AGX_TABLE_PEEK");
        if (peek && *peek && r == 0 && table_size) {
            printf(",\"peek\":[");
            for (const char *q = peek; *q;) {
                char *e; unsigned long wi = strtoul(q, &e, 0);
                require(e != q && (wi + 1) * 4 <= table_size, "table-peek-index");
                uint32_t v; memcpy(&v, data.map + table_off + wi * 4, 4);
                printf("%s%u", q == peek ? "" : ",", v);
                q = *e == ',' ? e + 1 : e;
                if (*e && *e != ',') require(0, "table-peek-syntax");
            }
            printf("]");
        }
        printf("}\n");
        require(r == 0, "syncobj-wait");
        struct drm_syncobj_array reset = {.handles = (uint64_t)(uintptr_t)&sc.handle, .count_handles = 1};
        io(DRM_IOCTL_SYNCOBJ_RESET, &reset, "syncobj-reset");
        /* AGX_REP_SLEEP_US: host pause between submissions (GPU idle time between them) */
        uint64_t pause = env("AGX_REP_SLEEP_US", 0);
        if (pause) { require(pause <= 1000000, "rep-sleep"); struct timespec q = {.tv_sec = (time_t)(pause / 1000000), .tv_nsec = (long)(pause % 1000000) * 1000}; nanosleep(&q, NULL); }
    }
    if (ce && *ce) {
        atomic_store(&echo_run, 0); pthread_join(echo_tid, NULL);
        const char *eo = getenv("AGX_CPU_ECHO_OUT");
        if (eo && *eo) { FILE *ef = fopen(eo, "wb"); require(ef != NULL && fwrite(echo_log, 16, echo_n, ef) == echo_n && fclose(ef) == 0, "cpu-echo-out"); }
        printf("{\"cpu_echo\":{\"observations\":%u}}\n", echo_n);
    }
    if (cw && *cw) {
        atomic_store(&clock_run, 0); pthread_join(clock_tid, NULL);
        uint64_t frq; __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frq));
        printf("{\"cpu_clock\":{\"iters\":%" PRIu64 ",\"cntvct\":[%" PRIu64 ",%" PRIu64 "],\"cntfrq\":%" PRIu64 ",\"flush\":%d}}\n",
               clock_iters, clock_t0, clock_t1, frq, (int)clock_flush);
    }
    const char *tout = getenv("AGX_TABLE_OUT");
    if (tout && *tout) {
        require(table_size > 0, "table-out-needs-table");
        FILE *t = fopen(tout, "wb"); require(t != NULL, "table-out-open");
        require(fwrite(data.map + table_off, 1, table_size, t) == table_size && fclose(t) == 0, "table-out-write");
    }
    FILE *o = fopen(argv[4], "wb"); require(o != NULL, "readback-open");
    require(fwrite(out, 4, words, o) == words && fclose(o) == 0, "readback-write");
    printf("{\"completed\":true,\"count\":%lu,\"words\":%u,\"repeats\":%lu}\n", count, words, reps);

    struct drm_asahi_queue_destroy qd = {.queue_id = qc.queue_id};
    io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &qd, "queue-destroy");
    /* AGX_CLEAN_EXIT: release every object explicitly instead of relying on process exit (which was found to leak
       the buffer objects' shmem in the kernel, 2026-10-16). 1 = munmap + GEM_CLOSE; 2 = also unbind first. */
    const int clean = (int)env("AGX_CLEAN_EXIT", 1);   /* default on: exit without it leaks every BO (shmem) */
    if (clean >= 2) {
        struct drm_asahi_gem_bind_object ub = {.op = DRM_ASAHI_BIND_OBJECT_OP_UNBIND, .object_handle = bo_ts.object_handle};
        io(DRM_IOCTL_ASAHI_GEM_BIND_OBJECT, &ub, "unbind-timestamps");
        struct bo *bs[2] = {&usc, &data};
        for (int i = 0; i < 2; i++) {
            struct drm_asahi_gem_bind_op op = {.flags = DRM_ASAHI_BIND_UNBIND, .range = bs[i]->size, .addr = bs[i]->va};
            struct drm_asahi_vm_bind vb = {.vm_id = vc.vm_id, .num_binds = 1, .stride = sizeof op, .userptr = (uint64_t)(uintptr_t)&op};
            io(DRM_IOCTL_ASAHI_VM_BIND, &vb, "vm-unbind");
        }
    }
    if (clean >= 1) {
        struct bo *bs[3] = {&usc, &data, &tsb};
        for (int i = 0; i < 3; i++) {
            require(munmap(bs[i]->map, bs[i]->size) == 0, "munmap");
            struct drm_gem_close gcl = {.handle = bs[i]->handle};
            io(DRM_IOCTL_GEM_CLOSE, &gcl, "gem-close");
        }
        struct drm_syncobj_destroy sd = {.handle = sc.handle};
        io(DRM_IOCTL_SYNCOBJ_DESTROY, &sd, "syncobj-destroy");
    }
    struct drm_asahi_vm_destroy vd = {.vm_id = vc.vm_id};
    io(DRM_IOCTL_ASAHI_VM_DESTROY, &vd, "vm-destroy");
    close(fd);
    return 0;
}
