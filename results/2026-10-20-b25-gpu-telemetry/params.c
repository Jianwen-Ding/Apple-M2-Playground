// B25: read-only query of DRM_ASAHI_GET_PARAMS and DRM_ASAHI_GET_TIME (no GPU work submitted)
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <string.h>
#include <sys/ioctl.h>
#include <drm/drm.h>
#include <drm/asahi_drm.h>
int main(void) {
  int fd = open("/dev/dri/renderD128", O_RDWR);
  if (fd < 0) { perror("open"); return 1; }
  struct drm_asahi_params_global p; memset(&p, 0, sizeof p);
  struct drm_asahi_get_params g = { .param_group = 0, .pointer = (__u64)(unsigned long)&p, .size = sizeof p };
  if (ioctl(fd, DRM_IOCTL_ASAHI_GET_PARAMS, &g)) { perror("get_params"); return 1; }
  printf("{\"features\":%llu,\"soft_faults\":%d,\"gpu_generation\":%u,\"gpu_variant\":%u,\"gpu_revision\":%u,\"chip_id\":%u,"
         "\"num_dies\":%u,\"num_clusters_total\":%u,\"num_cores_per_cluster\":%u,\"max_frequency_khz\":%u,"
         "\"vm_start\":%llu,\"vm_end\":%llu,\"max_commands_per_submission\":%u,\"max_attachments\":%u,"
         "\"command_timestamp_frequency_hz\":%llu,\"core_masks\":[",
         (unsigned long long)p.features, (int)(p.features & DRM_ASAHI_FEATURE_SOFT_FAULTS), p.gpu_generation, p.gpu_variant,
         p.gpu_revision, p.chip_id, p.num_dies, p.num_clusters_total, p.num_cores_per_cluster, p.max_frequency_khz,
         (unsigned long long)p.vm_start, (unsigned long long)p.vm_end, p.max_commands_per_submission, p.max_attachments,
         (unsigned long long)p.command_timestamp_frequency_hz);
  for (unsigned i = 0; i < p.num_clusters_total && i < DRM_ASAHI_MAX_CLUSTERS; i++) printf("%s\"0x%llx\"", i ? "," : "", (unsigned long long)p.core_masks[i]);
  struct drm_asahi_get_time t0 = {0}, t1 = {0}; struct timespec a, b;
  clock_gettime(CLOCK_MONOTONIC, &a); ioctl(fd, DRM_IOCTL_ASAHI_GET_TIME, &t0);
  usleep(200000);
  clock_gettime(CLOCK_MONOTONIC, &b); ioctl(fd, DRM_IOCTL_ASAHI_GET_TIME, &t1);
  double host_ns = (b.tv_sec - a.tv_sec) * 1e9 + (b.tv_nsec - a.tv_nsec);
  printf("],\"get_time_ticks_per_host_ns\":%.6f}\n", (double)(t1.gpu_timestamp - t0.gpu_timestamp) / host_ns);
  close(fd); return 0;
}
