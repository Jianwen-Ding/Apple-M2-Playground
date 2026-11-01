// vis: a kernel writes the iteration number to N words; after the launch's stream sync the CPU reads them all
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>
typedef int CUresult; typedef void *CUcontext; typedef uint64_t CUdeviceptr; typedef void *CUstream; typedef void *CUmodule; typedef void *CUfunction;
CUresult cuInit(unsigned); CUresult cuDevicePrimaryCtxRetain(CUcontext *, int); CUresult cuCtxSetCurrent(CUcontext);
CUresult cuMemAllocHost_v2(void **, size_t); CUresult cuMemHostGetDevicePointer_v2(CUdeviceptr *, void *, unsigned);
CUresult cuStreamCreate(CUstream *, unsigned); CUresult cuStreamSynchronize(CUstream);
CUresult cuModuleLoadData(CUmodule *, const void *); CUresult cuModuleGetFunction(CUfunction *, CUmodule, const char *);
CUresult cuLaunchKernel(CUfunction, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, CUstream, void **, void **);
CUresult cuMemAlloc_v2(CUdeviceptr *, size_t); CUresult cuMemcpyDtoH_v2(void *, CUdeviceptr, size_t);
#define CK(x) do { int e = (x); if (e) { fprintf(stderr, "%s: %d\n", #x, e); exit(1); } } while (0)
static const char *ptx = ".version 7.0\n.target sm_75\n.address_size 64\n.visible .entry k(.param .u64 p, .param .u32 v)\n{\n"
    ".reg .u32 %r<5>;\n.reg .u64 %rd<4>;\nld.param.u64 %rd1, [p];\nld.param.u32 %r1, [v];\nmov.u32 %r2, %ctaid.x;\nmov.u32 %r3, %tid.x;\n"
    "mad.lo.u32 %r4, %r2, 256, %r3;\nmul.wide.u32 %rd2, %r4, 4;\nadd.u64 %rd3, %rd1, %rd2;\nst.global.u32 [%rd3], %r1;\nret;\n}\n";
int main(int argc, char **argv) {
    int n = 1 << 20, it = atoi(argv[1]);
    CUcontext c; CK(cuInit(0)); CK(cuDevicePrimaryCtxRetain(&c, 0)); CK(cuCtxSetCurrent(c));
    CUstream s; CK(cuStreamCreate(&s, 1));
    CUmodule m; CK(cuModuleLoadData(&m, ptx)); CUfunction f; CK(cuModuleGetFunction(&f, m, "k"));
    CUdeviceptr d; CK(cuMemAlloc_v2(&d, n * 4)); uint32_t *h = malloc(n * 4);
    // the device buffer is mapped CPU-visible in zluda_agx: read it back with a DtoH copy (a CPU memcpy there)
    long bad = 0;
    for (uint32_t i = 1; i <= (uint32_t)it; i++) {
        void *args[] = {&d, &i};
        CK(cuLaunchKernel(f, n / 256, 1, 1, 256, 1, 1, 0, s, args, NULL));
        CK(cuStreamSynchronize(s));
        CK(cuMemcpyDtoH_v2(h, d, n * 4));
        for (int j = 0; j < n; j++) if (h[j] != i) { bad++; if (bad < 5) fprintf(stderr, "iter %u word %d = %u\n", i, j, h[j]); }
    }
    printf("%d iterations, %ld stale words\n", it, bad);
    return 0;
}
