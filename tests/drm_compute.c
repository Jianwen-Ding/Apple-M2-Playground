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
 * usage: drm_compute node code.bin count readback repeats [gprs]
 * Bounded: count <= 65536, repeats <= 64, 3 s wait per submit. */
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
static void put64(uint8_t *p, uint64_t v) { memcpy(p, &v, 8); }

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    require(argc == 6 || argc == 7, "usage: node code.bin count readback repeats [gprs]");
    char *end;
    unsigned long count = strtoul(argv[3], &end, 10); require(*end == 0 && count >= 1 && count <= 65536, "count");
    unsigned long reps = strtoul(argv[5], &end, 10); require(*end == 0 && reps >= 1 && reps <= 64, "repeats");
    unsigned long gprs = argc == 7 ? strtoul(argv[6], &end, 10) : 8;
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
    uint64_t usc_size = (0x2000 + code_size + 64 + page - 1) & ~(page - 1);
    uint32_t rounded = (uint32_t)((count + 31) / 32 * 32), words = 8 + rounded + 8 + 16;
    uint64_t data_size = (0x8000 + (uint64_t)words * 4 + page - 1) & ~(page - 1);
    struct bo usc = bo_create(usc_size, vc.vm_id, shader_base, DRM_ASAHI_BIND_READ);
    struct bo data = bo_create(data_size, vc.vm_id, data_base, DRM_ASAHI_BIND_READ | DRM_ASAHI_BIND_WRITE);
    struct bo tsb = bo_create(page, vc.vm_id, 0, 0);
    struct drm_asahi_gem_bind_object bo_ts = {.op = DRM_ASAHI_BIND_OBJECT_OP_BIND, .flags = DRM_ASAHI_BIND_OBJECT_USAGE_TIMESTAMPS,
                                              .handle = tsb.handle, .range = page};
    io(DRM_IOCTL_ASAHI_GEM_BIND_OBJECT, &bo_ts, "bind-timestamps");

    /* USC BO: pipeline words at 0x1000, code at 0x2000 (USC-relative = BO offset). */
    const uint32_t usc_words = 0x1000, code_off = 0x2000;
    memcpy(usc.map + code_off, code, code_size);
    const uint64_t unif_va = data.va + 0x0, out_va = data.va + 0x8000, cdm_va = data.va + 0x4000;
    uint8_t *w = usc.map + usc_words;
    /* USC Uniform: tag 0x1d, start halfs 8 (u4), size 8 halfs (u4..u7), buffer >> 2 at bit 26. */
    put64(w, 0x1dull | (8ull << 8) | (8ull << 20) | ((unif_va >> 2) << 26)); w += 8;
    /* USC Shared, none: tag 0x4d, layout vertex/compute 0x24 at bit 10, bytes 65536 -> groups(256) of 8 bits = 0 ("all"). */
    put32(w, 0x4du | (0x24u << 10)); w += 4;
    /* USC Shader: tag 0x0d, unk_2 = 3 at bit 10 (compute), code address at bit 16 (6 bytes). */
    uint64_t sh = 0x0dull | (3ull << 10) | ((uint64_t)code_off << 16); memcpy(w, &sh, 6); w += 6;
    /* USC Registers: tag 0x8d, register count groups(8) at bit 8 (5 bits, 0 = 256), unk_4 = 1 at bit 24. */
    uint32_t rc = (uint32_t)((gprs + 7) / 8) & 31; put32(w, 0x8du | (rc << 8) | (1u << 24)); w += 4;
    /* USC No preshader: tag 0x88 (2 bytes). */
    w[0] = 0x88; w[1] = 0; w += 2;
    printf("{\"usc_words_hex\":\"");
    for (uint8_t *q = usc.map + usc_words; q < w; q++) printf("%02x", *q);
    printf("\"}\n");

    /* Uniforms u4 = 0, u5 = count, u6_u7 = output VA. */
    put32(data.map + 0, 0); put32(data.map + 4, (uint32_t)count); put64(data.map + 8, out_va);

    /* CDM control stream. */
    uint8_t *c = data.map + 0x4000;
    put32(c, 1u << 1); c += 4;                 /* Launch word 0: uniform count groups(64) = 1; direct; block type 0 */
    put32(c, usc_words); c += 4;               /* Launch word 1: pipeline (64 B aligned, USC relative) */
    if (g14x) { put32(c, 0); put32(c + 4, 1u << 30); c += 8; }
    put32(c, rounded); put32(c + 4, 1); put32(c + 8, 1); c += 12;   /* global size in threads */
    put32(c, 32); put32(c + 4, 1); put32(c + 8, 1); c += 12;        /* local size */
    put32(c, (3u << 29) | 0xfffffu); c += 4;   /* Barrier: Mesa's unk0..19 incl. USC cache invalidate */
    put32(c, 2u << 29); put32(c + 4, 0); c += 8;  /* Stream terminate */
    uint64_t cdm_end = cdm_va + (uint64_t)(c - (data.map + 0x4000));
    printf("{\"cdm_hex\":\"");
    for (uint8_t *q = data.map + 0x4000; q < c; q++) printf("%02x", *q);
    printf("\"}\n");

    struct drm_asahi_queue_create qc = {.vm_id = vc.vm_id, .priority = DRM_ASAHI_PRIORITY_MEDIUM, .usc_exec_base = shader_base};
    io(DRM_IOCTL_ASAHI_QUEUE_CREATE, &qc, "queue-create");
    struct drm_syncobj_create sc = {0};
    io(DRM_IOCTL_SYNCOBJ_CREATE, &sc, "syncobj-create");

    uint32_t *out = (uint32_t *)(data.map + 0x8000);
    for (unsigned long rep = 0; rep < reps; rep++) {
        for (uint32_t j = 0; j < words; j++) out[j] = j < words - 16 ? 0xcdcdcdcdu : 0xa5a50000u + j - (words - 16);
        memset(tsb.map, 0, 32);
        struct { struct drm_asahi_cmd_header h; struct drm_asahi_cmd_compute c; } cmd = {
            .h = {.cmd_type = DRM_ASAHI_CMD_COMPUTE, .size = sizeof(struct drm_asahi_cmd_compute),
                  .vdm_barrier = DRM_ASAHI_BARRIER_NONE, .cdm_barrier = 0},
            .c = {.cdm_ctrl_stream_base = cdm_va, .cdm_ctrl_stream_end = cdm_end,
                  .ts = {.start = {.handle = bo_ts.object_handle, .offset = 0},
                         .end = {.handle = bo_ts.object_handle, .offset = 8}}},
        };
        struct drm_asahi_sync out_sync = {.sync_type = DRM_ASAHI_SYNC_SYNCOBJ, .handle = sc.handle};
        struct drm_asahi_submit sub = {.syncs = (uint64_t)(uintptr_t)&out_sync, .cmdbuf = (uint64_t)(uintptr_t)&cmd,
                                       .queue_id = qc.queue_id, .out_sync_count = 1, .cmdbuf_size = sizeof cmd};
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
        printf("{\"rep\":%lu,\"wait\":%d,\"errno\":%d,\"host_ns\":%" PRIu64 ",\"fw_ts\":[%" PRIu64 ",%" PRIu64 "],\"drm_time\":[%" PRIu64 ",%" PRIu64 "]}\n",
               rep, r, r ? errno : 0, h1 - h0, ts[0], ts[1], (uint64_t)t0.gpu_timestamp, (uint64_t)t1.gpu_timestamp);
        require(r == 0, "syncobj-wait");
        struct drm_syncobj_array reset = {.handles = (uint64_t)(uintptr_t)&sc.handle, .count_handles = 1};
        io(DRM_IOCTL_SYNCOBJ_RESET, &reset, "syncobj-reset");
    }
    FILE *o = fopen(argv[4], "wb"); require(o != NULL, "readback-open");
    require(fwrite(out, 4, words, o) == words && fclose(o) == 0, "readback-write");
    printf("{\"completed\":true,\"count\":%lu,\"words\":%u,\"repeats\":%lu}\n", count, words, reps);

    struct drm_asahi_queue_destroy qd = {.queue_id = qc.queue_id};
    io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &qd, "queue-destroy");
    struct drm_asahi_vm_destroy vd = {.vm_id = vc.vm_id};
    io(DRM_IOCTL_ASAHI_VM_DESTROY, &vd, "vm-destroy");
    close(fd);
    return 0;
}
