// B1 data trace: LD_PRELOAD shim that records Mesa's asahi uAPI traffic and, on every SUBMIT that contains a
// compute command, dumps the command struct and the contents of every bound GPU buffer (read-only mappings).
// Output: $ASAHI_TRACE_DIR/submit-N/{manifest.json, bo-<va>.bin}. Nothing is modified or submitted by the shim.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <drm/drm.h>
#include <drm/asahi_drm.h>

#define MAXB 4096
static struct { uint32_t handle; uint64_t size; } bos[MAXB]; static int nbos;
static struct { uint64_t addr, range, offset; uint32_t handle; } binds[MAXB]; static int nbinds;
static uint64_t usc_base; static int nsubmit; static int drm_fd = -1;

static uint64_t bo_size(uint32_t h) { for (int i = 0; i < nbos; i++) if (bos[i].handle == h) return bos[i].size; return 0; }

static int (*real_ioctl)(int, unsigned long, ...);

static void dump_bind(FILE *m, const char *dir, int i, int first) {
  uint64_t cap = 64ull << 20, n = binds[i].range < cap ? binds[i].range : cap;
  struct drm_asahi_gem_mmap_offset mo = { .handle = binds[i].handle };
  int ok = real_ioctl(drm_fd, DRM_IOCTL_ASAHI_GEM_MMAP_OFFSET, &mo) == 0;
  void *p = ok ? mmap(NULL, bo_size(binds[i].handle), PROT_READ, MAP_SHARED, drm_fd, mo.offset) : MAP_FAILED;
  fprintf(m, "%s{\"va\":\"0x%llx\",\"range\":%llu,\"bo_offset\":%llu,\"handle\":%u,\"bo_size\":%llu,\"dumped\":%llu}",
          first ? "" : ",", (unsigned long long)binds[i].addr, (unsigned long long)binds[i].range,
          (unsigned long long)binds[i].offset, binds[i].handle, (unsigned long long)bo_size(binds[i].handle),
          (unsigned long long)(p == MAP_FAILED ? 0 : n));
  if (p == MAP_FAILED) return;
  char path[512]; snprintf(path, sizeof path, "%s/bo-%llx.bin", dir, (unsigned long long)binds[i].addr);
  FILE *f = fopen(path, "wb"); if (f) { fwrite((char *)p + binds[i].offset, 1, n, f); fclose(f); }
  munmap(p, bo_size(binds[i].handle));
}

static void on_submit(struct drm_asahi_submit *s) {
  char *cb = (char *)(uintptr_t)s->cmdbuf; uint32_t off = 0; int has_compute = 0;
  while (off + sizeof(struct drm_asahi_cmd_header) <= s->cmdbuf_size) {
    struct drm_asahi_cmd_header *h = (void *)(cb + off);
    if (h->cmd_type == DRM_ASAHI_CMD_COMPUTE) has_compute = 1;
    off += sizeof *h + h->size;
  }
  if (!has_compute) return;
  const char *root = getenv("ASAHI_TRACE_DIR"); if (!root) root = "/tmp/asahi-trace";
  char dir[400]; snprintf(dir, sizeof dir, "%s/submit-%d", root, nsubmit++); mkdir(root, 0755); mkdir(dir, 0755);
  char path[512]; snprintf(path, sizeof path, "%s/manifest.json", dir);
  FILE *m = fopen(path, "w"); if (!m) return;
  fprintf(m, "{\"usc_exec_base\":\"0x%llx\",\"queue_id\":%u,\"flags\":%u,\"commands\":[", (unsigned long long)usc_base, s->queue_id, s->flags);
  off = 0; int first = 1;
  while (off + sizeof(struct drm_asahi_cmd_header) <= s->cmdbuf_size) {
    struct drm_asahi_cmd_header *h = (void *)(cb + off);
    fprintf(m, "%s{\"type\":%u,\"size\":%u,\"vdm_barrier\":%u,\"cdm_barrier\":%u", first ? "" : ",", h->cmd_type, h->size, h->vdm_barrier, h->cdm_barrier);
    if (h->cmd_type == DRM_ASAHI_CMD_COMPUTE) {
      struct drm_asahi_cmd_compute *c = (void *)(h + 1);
      fprintf(m, ",\"cflags\":%u,\"sampler_count\":%u,\"cdm_base\":\"0x%llx\",\"cdm_end\":\"0x%llx\",\"sampler_heap\":\"0x%llx\","
                 "\"helper_binary\":\"0x%x\",\"helper_cfg\":\"0x%x\",\"helper_data\":\"0x%llx\"",
              c->flags, c->sampler_count, (unsigned long long)c->cdm_ctrl_stream_base, (unsigned long long)c->cdm_ctrl_stream_end,
              (unsigned long long)c->sampler_heap, c->helper.binary, c->helper.cfg, (unsigned long long)c->helper.data);
    }
    fprintf(m, ",\"raw\":\""); for (unsigned k = 0; k < h->size; k++) fprintf(m, "%02x", (unsigned char)cb[off + sizeof *h + k]);
    fprintf(m, "\"}"); first = 0; off += sizeof *h + h->size;
  }
  fprintf(m, "],\"binds\":[");
  for (int i = 0; i < nbinds; i++) dump_bind(m, dir, i, i == 0);
  fprintf(m, "]}\n"); fclose(m);
}

int ioctl(int fd, unsigned long req, ...) {
  va_list ap; va_start(ap, req); void *arg = va_arg(ap, void *); va_end(ap);
  if (!real_ioctl) real_ioctl = dlsym(RTLD_NEXT, "ioctl");
  if (req == DRM_IOCTL_ASAHI_SUBMIT) { drm_fd = fd; on_submit(arg); }
  int r = real_ioctl(fd, req, arg);
  if (r) return r;
  if (req == DRM_IOCTL_ASAHI_GEM_CREATE && nbos < MAXB) {
    struct drm_asahi_gem_create *g = arg; bos[nbos].handle = g->handle; bos[nbos++].size = g->size; drm_fd = fd;
  } else if (req == DRM_IOCTL_ASAHI_VM_BIND) {
    struct drm_asahi_vm_bind *b = arg;
    for (unsigned i = 0; i < b->num_binds; i++) {
      struct drm_asahi_gem_bind_op *op = (void *)((char *)(uintptr_t)b->userptr + i * b->stride);
      // drop any previous bind that overlaps this range, then record a map (unbinds only drop)
      for (int k = 0; k < nbinds; k++)
        if (binds[k].addr < op->addr + op->range && op->addr < binds[k].addr + binds[k].range) binds[k--] = binds[--nbinds];
      if (!(op->flags & DRM_ASAHI_BIND_UNBIND) && nbinds < MAXB) {
        binds[nbinds].addr = op->addr; binds[nbinds].range = op->range; binds[nbinds].offset = op->offset; binds[nbinds++].handle = op->handle;
      }
    }
  } else if (req == DRM_IOCTL_ASAHI_QUEUE_CREATE) {
    struct drm_asahi_queue_create *q = arg; usc_base = q->usc_exec_base;
  }
  return r;
}
