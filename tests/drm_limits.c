/* Host-side limits of the Asahi DRM interface (simulator task safe-12 step 2).
 *
 * Submits no GPU work: no DRM_IOCTL_ASAHI_SUBMIT is issued, so no shader runs.
 * Every probe is a kernel-validated ioctl whose success or errno is recorded. Physical memory
 * use is bounded: regular binds pin at most AGX_LIMITS_MAX_BIND bytes (default 4 GiB); larger
 * VA ranges use DRM_ASAHI_BIND_SINGLE_PAGE, which pins one 16 KiB page.
 * Output: one JSON object per line.
 *
 * usage: drm_limits /dev/dri/renderD128 */
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
#include <unistd.h>

static int fd = -1;
static const uint64_t PAGE = 16384;

static int try_io(unsigned long req, void *arg)
{
    int r; do r = ioctl(fd, req, arg); while (r < 0 && (errno == EINTR || errno == EAGAIN));
    return r == 0 ? 0 : errno;
}
static void fatal(const char *stage, int e) { printf("{\"failure\":\"%s\",\"errno\":%d}\n", stage, e); exit(1); }

static struct drm_asahi_params_global p;

static int vm_create(uint32_t *id)
{
    uint64_t ksize = p.vm_kernel_min_size > (32ull << 30) ? p.vm_kernel_min_size : (32ull << 30);
    struct drm_asahi_vm_create vc = {.kernel_start = p.vm_end - ksize, .kernel_end = p.vm_end};
    int e = try_io(DRM_IOCTL_ASAHI_VM_CREATE, &vc); *id = vc.vm_id; return e;
}
static void vm_destroy(uint32_t id) { struct drm_asahi_vm_destroy d = {.vm_id = id}; try_io(DRM_IOCTL_ASAHI_VM_DESTROY, &d); }
static int gem_create(uint64_t size, uint32_t flags, uint32_t vm, uint32_t *h)
{
    struct drm_asahi_gem_create gc = {.size = size, .flags = flags, .vm_id = vm};
    int e = try_io(DRM_IOCTL_ASAHI_GEM_CREATE, &gc); *h = gc.handle; return e;
}
static void gem_close(uint32_t h) { struct drm_gem_close c = {.handle = h}; try_io(DRM_IOCTL_GEM_CLOSE, &c); }
static int bind(uint32_t vm, uint32_t flags, uint32_t h, uint64_t off, uint64_t range, uint64_t addr)
{
    struct drm_asahi_gem_bind_op op = {.flags = flags, .handle = h, .offset = off, .range = range, .addr = addr};
    struct drm_asahi_vm_bind vb = {.vm_id = vm, .num_binds = 1, .stride = sizeof op, .userptr = (uint64_t)(uintptr_t)&op};
    return try_io(DRM_IOCTL_ASAHI_VM_BIND, &vb);
}
static int unbind(uint32_t vm, uint64_t range, uint64_t addr) { return bind(vm, DRM_ASAHI_BIND_UNBIND, 0, 0, range, addr); }

int main(int argc, char **argv)
{
    if (argc != 2) { fprintf(stderr, "usage: %s /dev/dri/renderDN\n", argv[0]); return 2; }
    fd = open(argv[1], O_RDWR | O_CLOEXEC); if (fd < 0) fatal("open", errno);
    const char *mb = getenv("AGX_LIMITS_MAX_BIND");
    uint64_t max_bind = mb ? strtoull(mb, NULL, 0) : (4ull << 30);

    /* 1. Every params_global field. */
    struct drm_asahi_get_params gp = {.param_group = 0, .pointer = (uint64_t)(uintptr_t)&p, .size = sizeof p};
    int e = try_io(DRM_IOCTL_ASAHI_GET_PARAMS, &gp); if (e) fatal("get-params", e);
    printf("{\"params\":{\"sizeof\":%zu,\"features\":%" PRIu64 ",\"gpu_generation\":%u,\"gpu_variant\":\"%c\",\"gpu_revision\":%u,"
           "\"chip_id\":\"%x\",\"num_dies\":%u,\"num_clusters_total\":%u,\"num_cores_per_cluster\":%u,\"max_frequency_khz\":%u,"
           "\"vm_start\":%" PRIu64 ",\"vm_end\":%" PRIu64 ",\"vm_kernel_min_size\":%" PRIu64 ",\"max_commands_per_submission\":%u,"
           "\"max_attachments\":%u,\"command_timestamp_frequency_hz\":%" PRIu64 ",\"core_masks\":[",
           sizeof p, (uint64_t)p.features, p.gpu_generation, (char)p.gpu_variant, p.gpu_revision, p.chip_id, p.num_dies,
           p.num_clusters_total, p.num_cores_per_cluster, p.max_frequency_khz, (uint64_t)p.vm_start, (uint64_t)p.vm_end,
           (uint64_t)p.vm_kernel_min_size, p.max_commands_per_submission, p.max_attachments,
           (uint64_t)p.command_timestamp_frequency_hz);
    for (uint32_t i = 0; i < p.num_clusters_total && i < DRM_ASAHI_MAX_CLUSTERS; i++) printf("%s%" PRIu64, i ? "," : "", (uint64_t)p.core_masks[i]);
    printf("]}}\n");
    /* Nonzero param_group and short / oversized buffers. */
    struct drm_asahi_params_global q; memset(&q, 0xab, sizeof q);
    struct drm_asahi_get_params g1 = {.param_group = 1, .pointer = (uint64_t)(uintptr_t)&q, .size = sizeof q};
    struct drm_asahi_get_params g2 = {.param_group = 0, .pointer = (uint64_t)(uintptr_t)&q, .size = 8};
    int e1 = try_io(DRM_IOCTL_ASAHI_GET_PARAMS, &g1), e2 = try_io(DRM_IOCTL_ASAHI_GET_PARAMS, &g2);
    int short_ok = e2 == 0 && q.features == p.features && q.gpu_generation == 0xabababab;
    static uint8_t big[4096]; struct drm_asahi_get_params g3 = {.param_group = 0, .pointer = (uint64_t)(uintptr_t)big, .size = sizeof big};
    int e3 = try_io(DRM_IOCTL_ASAHI_GET_PARAMS, &g3);
    printf("{\"get_params\":{\"group1_errno\":%d,\"size8_errno\":%d,\"size8_wrote_only_8\":%d,\"size4096_errno\":%d}}\n", e1, e2, short_ok, e3);

    /* 2. GET_TIME and its flags. */
    struct drm_asahi_get_time t0 = {0}, t1 = {.flags = 1};
    int te0 = try_io(DRM_IOCTL_ASAHI_GET_TIME, &t0), te1 = try_io(DRM_IOCTL_ASAHI_GET_TIME, &t1);
    printf("{\"get_time\":{\"errno\":%d,\"ts\":%" PRIu64 ",\"flags1_errno\":%d}}\n", te0, (uint64_t)t0.gpu_timestamp, te1);

    /* 3. VM creation: bad kernel ranges, then how many VMs one process may hold (capped at 256). */
    {
        struct drm_asahi_vm_create small = {.kernel_start = p.vm_end - PAGE, .kernel_end = p.vm_end};
        struct drm_asahi_vm_create outside = {.kernel_start = p.vm_end, .kernel_end = p.vm_end + (32ull << 30)};
        struct drm_asahi_vm_create flipped = {.kernel_start = p.vm_end, .kernel_end = p.vm_end - (32ull << 30)};
        int a = try_io(DRM_IOCTL_ASAHI_VM_CREATE, &small); if (!a) vm_destroy(small.vm_id);
        int b = try_io(DRM_IOCTL_ASAHI_VM_CREATE, &outside); if (!b) vm_destroy(outside.vm_id);
        int c = try_io(DRM_IOCTL_ASAHI_VM_CREATE, &flipped); if (!c) vm_destroy(flipped.vm_id);
        printf("{\"vm_create_bad\":{\"kernel_one_page_errno\":%d,\"kernel_outside_errno\":%d,\"kernel_flipped_errno\":%d}}\n", a, b, c);
        static uint32_t ids[256]; int n = 0, last = 0;
        while (n < 256 && !(last = vm_create(&ids[n]))) n++;
        printf("{\"vm_count\":{\"created\":%d,\"cap\":256,\"stop_errno\":%d}}\n", n, last);
        for (int i = 0; i < n; i++) vm_destroy(ids[i]);
    }

    uint32_t vm; e = vm_create(&vm); if (e) fatal("vm-create", e);
    uint64_t va = (p.vm_start > (1ull << 36) ? p.vm_start : (1ull << 36));
    va = (va + 0xffffffffull) & ~0xffffffffull;

    /* 4. GEM create: flags, sizes (create alone pins no memory; doubling to 64 GiB). */
    {
        uint32_t h; int fl[6]; uint32_t flags[6] = {0, DRM_ASAHI_GEM_WRITEBACK, DRM_ASAHI_GEM_VM_PRIVATE, 1u << 2, 1u << 31, 0};
        for (int i = 0; i < 5; i++) {
            fl[i] = gem_create(PAGE, flags[i], flags[i] & DRM_ASAHI_GEM_VM_PRIVATE ? vm : 0, &h); if (!fl[i]) gem_close(h);
        }
        fl[5] = gem_create(PAGE, 0, vm, &h); if (!fl[5]) gem_close(h); /* vm_id without VM_PRIVATE */
        int z = gem_create(0, 0, 0, &h); if (!z) gem_close(h);
        int odd = gem_create(PAGE + 4096, 0, 0, &h); if (!odd) gem_close(h);

        printf("{\"gem_flags\":{\"none\":%d,\"writeback\":%d,\"vm_private\":%d,\"bit2\":%d,\"bit31\":%d,\"vm_id_without_private\":%d,"
               "\"size0\":%d,\"size_unaligned_20k\":%d}}\n", fl[0], fl[1], fl[2], fl[3], fl[4], fl[5], z, odd);
        uint64_t s = PAGE, ok = 0; int last = 0;
        while (s <= (64ull << 30)) { last = gem_create(s, 0, 0, &h); if (last) break; gem_close(h); ok = s; s <<= 1; }
        printf("{\"gem_size\":{\"largest_ok\":%" PRIu64 ",\"cap\":%" PRIu64 ",\"stop_errno\":%d}}\n", ok, (uint64_t)(64ull << 30), last);
    }

    /* 5. VM_BIND: alignment, permissions, VA window, regular range up to max_bind, single-page ranges. */
    {
        uint32_t h; e = gem_create(4 * PAGE, DRM_ASAHI_GEM_WRITEBACK, 0, &h); if (e) fatal("gem-small", e);
        int rw = bind(vm, DRM_ASAHI_BIND_READ | DRM_ASAHI_BIND_WRITE, h, 0, 4 * PAGE, va); if (!rw) unbind(vm, 4 * PAGE, va);
        int ro = bind(vm, DRM_ASAHI_BIND_READ, h, 0, 4 * PAGE, va); if (!ro) unbind(vm, 4 * PAGE, va);
        int wo = bind(vm, DRM_ASAHI_BIND_WRITE, h, 0, 4 * PAGE, va); if (!wo) unbind(vm, 4 * PAGE, va);
        int none = bind(vm, 0, h, 0, 4 * PAGE, va); if (!none) unbind(vm, 4 * PAGE, va);
        int una = bind(vm, DRM_ASAHI_BIND_READ, h, 0, 4 * PAGE, va + 4096); if (!una) unbind(vm, 4 * PAGE, va + 4096);
        int uoff = bind(vm, DRM_ASAHI_BIND_READ, h, 4096, PAGE, va); if (!uoff) unbind(vm, PAGE, va);
        int past = bind(vm, DRM_ASAHI_BIND_READ, h, 0, 8 * PAGE, va); if (!past) unbind(vm, 8 * PAGE, va);
        int below = bind(vm, DRM_ASAHI_BIND_READ, h, 0, PAGE, p.vm_start >= PAGE ? p.vm_start - PAGE : 0);
        if (!below) unbind(vm, PAGE, p.vm_start - PAGE);
        int inkern = bind(vm, DRM_ASAHI_BIND_READ, h, 0, PAGE, p.vm_end - PAGE); if (!inkern) unbind(vm, PAGE, p.vm_end - PAGE);
        int beyond = bind(vm, DRM_ASAHI_BIND_READ, h, 0, PAGE, p.vm_end); if (!beyond) unbind(vm, PAGE, p.vm_end);
        int lowest = bind(vm, DRM_ASAHI_BIND_READ, h, 0, PAGE, p.vm_start); if (!lowest) unbind(vm, PAGE, p.vm_start);
        int twice_a = bind(vm, DRM_ASAHI_BIND_READ, h, 0, PAGE, va);
        int twice_b = bind(vm, DRM_ASAHI_BIND_READ, h, PAGE, PAGE, va); /* overlapping bind on a bound range */
        unbind(vm, PAGE, va);
        int unb_empty = unbind(vm, PAGE, va + (1ull << 30));
        int badflag = bind(vm, DRM_ASAHI_BIND_READ | (1u << 4), h, 0, PAGE, va); if (!badflag) unbind(vm, PAGE, va);
        int sp_small = bind(vm, DRM_ASAHI_BIND_READ | DRM_ASAHI_BIND_SINGLE_PAGE, h, 0, 1024 * PAGE, va);
        if (!sp_small) unbind(vm, 1024 * PAGE, va);
        printf("{\"vm_bind\":{\"rw\":%d,\"read_only\":%d,\"write_only\":%d,\"no_perm\":%d,\"va_unaligned_4k\":%d,\"offset_unaligned_4k\":%d,"
               "\"range_past_bo\":%d,\"below_vm_start\":%d,\"top_page_of_vm\":%d,\"at_vm_end\":%d,\"at_vm_start\":%d,"
               "\"first_bind\":%d,\"overlapping_rebind\":%d,\"unbind_unmapped\":%d,\"flag_bit4\":%d,\"single_page_16MiB\":%d}}\n",
               rw, ro, wo, none, una, uoff, past, below, inkern, beyond, lowest, twice_a, twice_b, unb_empty, badflag, sp_small);
        /* Single-page binds over growing ranges: one physical page, page-table cost only. */
        uint64_t r = 1ull << 30, okr = 0; int last = 0;
        while (r <= (64ull << 30)) {
            last = bind(vm, DRM_ASAHI_BIND_READ | DRM_ASAHI_BIND_SINGLE_PAGE, h, 0, r, va); if (last) break;
            unbind(vm, r, va); okr = r; r <<= 1;
        }
        printf("{\"single_page_range\":{\"largest_ok\":%" PRIu64 ",\"cap\":%" PRIu64 ",\"stop_errno\":%d}}\n", okr, (uint64_t)(64ull << 30), last);
        gem_close(h);
        /* Regular bind of growing BOs, pinning real memory, up to max_bind. */
        uint64_t s = 64ull << 20, oks = 0; last = 0;
        while (s <= max_bind) {
            uint32_t hb; last = gem_create(s, 0, 0, &hb); if (last) break;
            last = bind(vm, DRM_ASAHI_BIND_READ | DRM_ASAHI_BIND_WRITE, hb, 0, s, va); if (!last) unbind(vm, s, va);
            gem_close(hb); if (last) break; oks = s; s <<= 1;
        }
        printf("{\"regular_bind\":{\"largest_ok\":%" PRIu64 ",\"cap\":%" PRIu64 ",\"stop_errno\":%d}}\n", oks, max_bind, last);
    }

    /* 6. Queues: priorities 0-4, bad flags / VM, then how many queues on one VM (capped at 64). */
    {
        int pe[5];
        for (uint32_t pr = 0; pr < 5; pr++) {
            struct drm_asahi_queue_create qc = {.vm_id = vm, .priority = pr, .usc_exec_base = va};
            pe[pr] = try_io(DRM_IOCTL_ASAHI_QUEUE_CREATE, &qc);
            if (!pe[pr]) { struct drm_asahi_queue_destroy qd = {.queue_id = qc.queue_id}; try_io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &qd); }
        }
        struct drm_asahi_queue_create bf = {.flags = 1, .vm_id = vm, .priority = 1, .usc_exec_base = va};
        int ebf = try_io(DRM_IOCTL_ASAHI_QUEUE_CREATE, &bf);
        if (!ebf) { struct drm_asahi_queue_destroy qd = {.queue_id = bf.queue_id}; try_io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &qd); }
        struct drm_asahi_queue_create bv = {.vm_id = 0xffff, .priority = 1, .usc_exec_base = va};
        int ebv = try_io(DRM_IOCTL_ASAHI_QUEUE_CREATE, &bv);
        if (!ebv) { struct drm_asahi_queue_destroy qd = {.queue_id = bv.queue_id}; try_io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &qd); }
        struct drm_asahi_queue_destroy dbad = {.queue_id = 0xffff};
        int edbad = try_io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &dbad);
        printf("{\"queue_create\":{\"priority_errno\":[%d,%d,%d,%d,%d],\"flags1\":%d,\"bad_vm\":%d,\"destroy_unknown\":%d}}\n",
               pe[0], pe[1], pe[2], pe[3], pe[4], ebf, ebv, edbad);
        static uint32_t qs[64]; int n = 0, last = 0;
        while (n < 64) {
            struct drm_asahi_queue_create qc = {.vm_id = vm, .priority = 0, .usc_exec_base = va};
            if ((last = try_io(DRM_IOCTL_ASAHI_QUEUE_CREATE, &qc))) break;
            qs[n++] = qc.queue_id;
        }
        printf("{\"queue_count\":{\"created\":%d,\"cap\":64,\"stop_errno\":%d}}\n", n, last);
        for (int i = 0; i < n; i++) { struct drm_asahi_queue_destroy qd = {.queue_id = qs[i]}; try_io(DRM_IOCTL_ASAHI_QUEUE_DESTROY, &qd); }
    }
    vm_destroy(vm);
    printf("{\"done\":true,\"submits\":0}\n");
    return 0;
}
