#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
#include <drm/asahi_drm.h>

/* Read-only queries only. Host brackets are diagnostics, never ISA timing. */
static uint64_t host_ns(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC_RAW, &ts)) {
        perror("clock_gettime");
        exit(1);
    }
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}

static unsigned bounded(const char *s, unsigned min, unsigned max)
{
    char *end;
    errno = 0;
    unsigned long n = strtoul(s, &end, 10);
    if (errno || !*s || *end || n < min || n > max) {
        fprintf(stderr, "Invalid bounded argument: %s\n", s);
        exit(2);
    }
    return (unsigned)n;
}

int main(int argc, char **argv)
{
    if (argc != 4) {
        fprintf(stderr, "Usage: %s DEVICE SAMPLES(2..256) INTERVAL_MS(0..20)\n", argv[0]);
        return 2;
    }
    unsigned count = bounded(argv[2], 2, 256);
    unsigned interval = bounded(argv[3], 0, 20);
    int fd = open(argv[1], O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        fprintf(stderr, "open(%s): errno=%d %s\n", argv[1], errno, strerror(errno));
        return 1;
    }
    char name[32] = {0};
    struct drm_version version = {.name_len = sizeof(name)-1, .name = name};
    if (ioctl(fd, DRM_IOCTL_VERSION, &version) < 0) {
        fprintf(stderr, "DRM_IOCTL_VERSION: errno=%d %s\n", errno, strerror(errno));
        close(fd);
        return 1;
    }
    if (version.name_len != 5 || strcmp(name, "asahi")) {
        fprintf(stderr, "Refusing non-asahi driver: %s\n", name);
        close(fd);
        return 1;
    }
    printf("{\"kind\":\"metadata\",\"driver\":\"asahi\",\"ioctl\":%lu,\"struct_size\":%zu,\"samples\":%u,\"interval_ms\":%u,\"host_clock\":\"CLOCK_MONOTONIC_RAW\",\"uapi_units\":\"nanoseconds\"}\n",
           (unsigned long)DRM_IOCTL_ASAHI_GET_TIME, sizeof(struct drm_asahi_get_time), count, interval);
    for (unsigned i = 0; i < count; i++) {
        if (i && interval) {
            struct timespec req = {.tv_nsec = (long)interval * 1000000};
            while (nanosleep(&req, &req)) {
                if (errno != EINTR) {
                    perror("nanosleep");
                    close(fd);
                    return 1;
                }
            }
        }
        struct drm_asahi_get_time query = {0};
        uint64_t before = host_ns();
        int ret = ioctl(fd, DRM_IOCTL_ASAHI_GET_TIME, &query);
        int error = ret < 0 ? errno : 0;
        uint64_t after = host_ns();
        printf("{\"kind\":\"sample\",\"index\":%u,\"host_before_ns\":%" PRIu64 ",\"host_after_ns\":%" PRIu64 ",\"flags\":%" PRIu64 ",\"gpu_timestamp_ns\":%" PRIu64 ",\"returncode\":%d,\"errno\":%d}\n",
               i, before, after, (uint64_t)query.flags, (uint64_t)query.gpu_timestamp, ret, error);
        if (ret < 0) {
            fprintf(stderr, "DRM_IOCTL_ASAHI_GET_TIME: errno=%d %s\n", error, strerror(error));
            close(fd);
            return 1;
        }
    }
    if (close(fd) < 0) {
        perror("close");
        return 1;
    }
    return 0;
}
