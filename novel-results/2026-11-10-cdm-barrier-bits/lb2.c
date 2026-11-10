// i-cache across dispatches: graph of 64 launches; mode same: k1 x64; alt: k1,k2 alternating; tiny: k0 x64
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
typedef int CUresult; typedef void *CUcontext, *CUmodule, *CUfunction, *CUstream, *CUevent, *CUgraph, *CUgraphExec;
typedef uint64_t CUdeviceptr;
CUresult cuInit(unsigned); CUresult cuDevicePrimaryCtxRetain(CUcontext *, int); CUresult cuCtxSetCurrent(CUcontext);
CUresult cuModuleLoadData(CUmodule *, const void *); CUresult cuModuleGetFunction(CUfunction *, CUmodule, const char *);
CUresult cuLaunchKernel(CUfunction, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, CUstream, void **, void **);
CUresult cuStreamCreate(CUstream *, unsigned); CUresult cuStreamBeginCapture_v2(CUstream, int); CUresult cuStreamEndCapture(CUstream, CUgraph *);
CUresult cuGraphInstantiateWithFlags(CUgraphExec *, CUgraph, unsigned long long); CUresult cuGraphLaunch(CUgraphExec, CUstream);
CUresult cuEventCreate(CUevent *, unsigned); CUresult cuEventRecord(CUevent, CUstream); CUresult cuEventSynchronize(CUevent);
CUresult cuEventElapsedTime(float *, CUevent, CUevent); CUresult cuMemAlloc_v2(CUdeviceptr *, size_t);
#define CK(x) do { int e_ = (x); if (e_) { fprintf(stderr, "%s: %d\n", #x, e_); exit(1); } } while (0)
int main(int argc, char **argv) {
    const char *mode = argv[1]; int n = 64;
    FILE *f = fopen("big.ptx", "rb"); fseek(f, 0, 2); long sz = ftell(f); rewind(f); char *ptx = calloc(sz + 1, 1); fread(ptx, 1, sz, f);
    CUcontext ctx; CK(cuInit(0)); CK(cuDevicePrimaryCtxRetain(&ctx, 0)); CK(cuCtxSetCurrent(ctx));
    CUmodule m; CK(cuModuleLoadData(&m, ptx)); CUfunction k0, k1, k2;
    CK(cuModuleGetFunction(&k0, m, "k0")); CK(cuModuleGetFunction(&k1, m, "k1")); CK(cuModuleGetFunction(&k2, m, "k2"));
    CUstream s; CK(cuStreamCreate(&s, 0)); CUdeviceptr buf; CK(cuMemAlloc_v2(&buf, 1 << 20));
    CUgraph g; CK(cuStreamBeginCapture_v2(s, 0));
    void *args[] = {&buf};
    for (int i = 0; i < n; i++) {
        CUfunction k = !strcmp(mode, "tiny") ? k0 : !strcmp(mode, "same") ? k1 : (i & 1 ? k2 : k1);
        CK(cuLaunchKernel(k, 1, 1, 1, 32, 1, 1, 0, s, args, 0));
    }
    CK(cuStreamEndCapture(s, &g)); CUgraphExec ge; CK(cuGraphInstantiateWithFlags(&ge, g, 0));
    CUevent a, b; CK(cuEventCreate(&a, 0)); CK(cuEventCreate(&b, 0));
    float best = 1e9; int R = 100;
    for (int r = 0; r < 5; r++) {
        CK(cuEventRecord(a, s)); for (int i = 0; i < R; i++) CK(cuGraphLaunch(ge, s)); CK(cuEventRecord(b, s)); CK(cuEventSynchronize(b));
        float ms; CK(cuEventElapsedTime(&ms, a, b)); ms /= R; if (ms < best) best = ms;
    }
    printf("%s: %.2f us/launch\n", mode, best * 1e3 / n);
    return 0;
}
