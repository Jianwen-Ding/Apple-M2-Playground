/* Host-only: GET_TIME (firmware ns) against CNTVCT_EL0 read just before and after (no GPU work). */
#include <drm/drm.h>
#include <drm/asahi_drm.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdint.h>
#include <sys/ioctl.h>
static inline uint64_t cnt(void){uint64_t v; __asm__ volatile("isb; mrs %0, cntvct_el0":"=r"(v)); return v;}
int main(void){ int fd=open("/dev/dri/renderD128",O_RDWR); uint64_t f; __asm__("mrs %0, cntfrq_el0":"=r"(f));
 for(int i=0;i<8;i++){ uint64_t a=cnt(); struct drm_asahi_get_time t={0}; ioctl(fd,DRM_IOCTL_ASAHI_GET_TIME,&t); uint64_t b=cnt();
  double mid=(a+b)/2.0*1e9/f; printf("cntfrq %lu gpu_ns %lu cnt_ns_mid %.0f diff %.0f bracket_ns %.0f\n",f,(unsigned long)t.gpu_timestamp,mid,(double)t.gpu_timestamp-mid,(b-a)*1e9/f);}
}
