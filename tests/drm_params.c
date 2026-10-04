#define _POSIX_C_SOURCE 200809L
#include <drm/asahi_drm.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

/* Read-only queries only: no VM, BO, queue, submission, or time query. */
static int query(int fd, const char *path)
{
    char name[256] = {0}, desc[512] = {0};
    struct drm_version version = {
        .name_len = sizeof(name) - 1, .name = name,
        .desc_len = sizeof(desc) - 1, .desc = desc,
    };
    printf("device=%s\nopen_flags=O_RDONLY|O_CLOEXEC\n", path);
    if (ioctl(fd, DRM_IOCTL_VERSION, &version) < 0) {
        int error = errno;
        fprintf(stderr, "DRM_IOCTL_VERSION: errno=%d (%s); device does not support this query or access failed\n",
                error, strerror(error));
        return 1;
    }
    printf("driver=%s\ndriver_version=%d.%d.%d\ndescription=%s\n", name,
           version.version_major, version.version_minor,
           version.version_patchlevel, desc);
    if (strcmp(name, "asahi") != 0) {
        fprintf(stderr, "Unsupported driver '%s': expected 'asahi'; no driver-specific ioctl issued\n", name);
        return 3;
    }

    struct drm_asahi_params_global params = {0};
    struct drm_asahi_get_params request = {
        .param_group = 0,
        .pointer = (uint64_t)(uintptr_t)&params,
        .size = sizeof(params),
    };
    printf("ioctl_get_params=0x%lx\nparam_group=0\nrequest_size=%zu\n",
           (unsigned long)DRM_IOCTL_ASAHI_GET_PARAMS, sizeof(params));
    if (ioctl(fd, DRM_IOCTL_ASAHI_GET_PARAMS, &request) < 0) {
        int error = errno;
        fprintf(stderr, "DRM_IOCTL_ASAHI_GET_PARAMS: errno=%d (%s); query failed (unsupported UAPI, permissions, or driver error); no fallback ABI attempted\n",
                error, strerror(error));
        return 1;
    }
    printf("returned_size=%" PRIu64 "\nparams_raw_hex=", (uint64_t)request.size);
    const unsigned char *bytes = (const unsigned char *)&params;
    for (size_t i = 0; i < sizeof(params); ++i)
        printf("%02x", bytes[i]);
    putchar('\n');
    if (request.size < sizeof(params)) {
        fprintf(stderr, "Incomplete parameter structure: returned size=%" PRIu64 ", required=%zu; refusing full-field interpretation\n",
                (uint64_t)request.size, sizeof(params));
        return 1;
    }
#define U32(field) printf(#field "=%" PRIu32 "\n", (uint32_t)params.field)
#define U64(field) printf(#field "=%" PRIu64 "\n", (uint64_t)params.field)
    printf("features=0x%016" PRIx64 "\n", (uint64_t)params.features);
    U32(gpu_generation);
    U32(gpu_variant);
    U32(gpu_revision);
    printf("chip_id=0x%08" PRIx32 "\n", (uint32_t)params.chip_id);
    U32(num_dies);
    U32(num_clusters_total);
    U32(num_cores_per_cluster);
    U32(max_frequency_khz);
    for (unsigned i = 0; i < DRM_ASAHI_MAX_CLUSTERS; ++i)
        printf("core_masks[%u]=0x%016" PRIx64 "\n", i, (uint64_t)params.core_masks[i]);
    U64(vm_start);
    U64(vm_end);
    U64(vm_kernel_min_size);
    U32(max_commands_per_submission);
    U32(max_attachments);
    U64(command_timestamp_frequency_hz);
    if (!params.num_clusters_total || params.num_clusters_total > DRM_ASAHI_MAX_CLUSTERS ||
        !params.num_cores_per_cluster || params.num_cores_per_cluster > 64) {
        fprintf(stderr, "Invalid topology dimensions; refusing derived core count\n");
        return 1;
    }
    unsigned enabled = 0;
    for (unsigned i = 0; i < params.num_clusters_total; ++i) {
        uint64_t mask = params.core_masks[i];
        if (params.num_cores_per_cluster < 64 && mask >> params.num_cores_per_cluster) {
            fprintf(stderr, "Core mask exceeds declared cluster width at cluster %u\n", i);
            return 1;
        }
        while (mask) {
            enabled += (unsigned)(mask & 1);
            mask >>= 1;
        }
    }
    printf("derived_enabled_core_count=%u\n", enabled);
    puts("PASS: Asahi global parameters queried; values are driver-reported, no shader executed.");
    return 0;
}

int main(int argc, char **argv)
{
    if (argc > 2) {
        fprintf(stderr, "Usage: %s [DRM-device]\n", argv[0]);
        return 2;
    }
    const char *path = argc == 2 ? argv[1] : "/dev/dri/renderD128";
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        int error = errno;
        fprintf(stderr, "open(%s): errno=%d (%s)\n", path, error, strerror(error));
        return 1;
    }
    int status = query(fd, path);
    if (close(fd) < 0) {
        perror("close");
        return 1;
    }
    return status;
}
