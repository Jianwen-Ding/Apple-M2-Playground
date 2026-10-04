#define _POSIX_C_SOURCE 200809L
#include <drm/drm.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

/* Minimal DRM access test; does not submit GPU work. */
int main(int argc, char **argv)
{
    if (argc > 2) {
        fprintf(stderr, "Usage: %s [DRM-device]\n", argv[0]);
        return 2;
    }
    const char *path = argc == 2 ? argv[1] : "/dev/dri/renderD128";
    int fd = open(path, O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        perror(path);
        return 1;
    }

    char name[256] = {0}, date[256] = {0}, desc[512] = {0};
    struct drm_version version = {
        .name_len = sizeof(name) - 1, .name = name,
        .date_len = sizeof(date) - 1, .date = date,
        .desc_len = sizeof(desc) - 1, .desc = desc,
    };
    if (ioctl(fd, DRM_IOCTL_VERSION, &version) < 0) {
        perror("DRM_IOCTL_VERSION");
        close(fd);
        return 1;
    }
    printf("Device: %s\nDriver: %s\nVersion: %d.%d.%d\nDescription: %s\n",
           path, name, version.version_major, version.version_minor,
           version.version_patchlevel, desc);
    if (close(fd) < 0) {
        perror("close");
        return 1;
    }
    puts("PASS: opened DRM device and queried driver successfully.");
    return 0;
}
