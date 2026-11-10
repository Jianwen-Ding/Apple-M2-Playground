// Per-dispatch GPU cost in one batched command: a graph of N launches of a tiny kernel, timed with events.
// usage: lb N grid block [ptrarg 0|1]
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
typedef int CUresult; typedef void *CUcontext, *CUmodule, *CUfunction, *CUstream, *CUevent, *CUgraph, *CUgraphExec;
typedef uint64_t CUdeviceptr;
CUresult cuInit(unsigned); CUresult cuDevicePrimaryCtxRetain(CUcontext *, int); CUresult cuCtxSetCurrent(CUcontext);
CUresult cuModuleLoadData(CUmodule *, const void *); CUresult cuModuleGetFunction(CUfunction *, CUmodule, const char *);
CUresult cuLaunchKernel(CUfunction, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, CUstream, void **, void **);
CUresult cuStreamCreate(CUstream *, unsigned); CUresult cuStreamBeginCapture_v2(CUstream, int); CUresult cuStreamEndCapture(CUstream, CUgraph *);
CUresult cuGraphInstantiateWithFlags(CUgraphExec *, CUgraph, unsigned long long); CUresult cuGraphLaunch(CUgraphExec, CUstream);
CUresult cuEventCreate(CUevent *, unsigned); CUresult cuEventRecord(CUevent, CUstream); CUresult cuEventSynchronize(CUevent);
CUresult cuEventElapsedTime(float *, CUevent, CUevent); CUresult cuStreamSynchronize(CUstream); CUresult cuMemAlloc_v2(CUdeviceptr *, size_t);
#define CK(x) do { int e_ = (x); if (e_) { fprintf(stderr, "%s: %d\n", #x, e_); exit(1); } } while (0)
static const char *ptx =
".version 7.0\n.target sm_80\n.address_size 64\n"
".visible .entry k(.param .u64 p, .param .u32 v) {\n .reg .u64 %rd<4>; .reg .u32 %r<4>; .reg .pred %q;\n"
" ld.param.u64 %rd1, [p]; ld.param.u32 %r1, [v]; mov.u32 %r2, %tid.x; setp.ne.u32 %q, %r2, 0; @%q bra END;\n"
" cvta.to.global.u64 %rd2, %rd1; st.global.u32 [%rd2], %r1;\nEND: ret; }\n";
int main(int argc, char **argv) {
    int n = atoi(argv[1]), grid = atoi(argv[2]), block = atoi(argv[3]), samep = argc > 4 ? atoi(argv[4]) : 1;
    CUcontext ctx; CK(cuInit(0)); CK(cuDevicePrimaryCtxRetain(&ctx, 0)); CK(cuCtxSetCurrent(ctx));
    CUmodule m; CK(cuModuleLoadData(&m, ptx)); CUfunction f; CK(cuModuleGetFunction(&f, m, "k"));
    CUstream s; CK(cuStreamCreate(&s, 0));
    CUdeviceptr buf; CK(cuMemAlloc_v2(&buf, 1 << 20));
    CUgraph g; CK(cuStreamBeginCapture_v2(s, 0));
    CUdeviceptr ps[1024]; unsigned vs[1024];
    for (int i = 0; i < n; i++) {
        ps[i] = samep ? buf : buf + 4096 * (i % 256); vs[i] = i;
        void *args[] = {&ps[i], &vs[i]};
        CK(cuLaunchKernel(f, grid, 1, 1, block, 1, 1, 0, s, args, 0));
    }
    CK(cuStreamEndCapture(s, &g)); CUgraphExec ge; CK(cuGraphInstantiateWithFlags(&ge, g, 0));
    CUevent a, b; CK(cuEventCreate(&a, 0)); CK(cuEventCreate(&b, 0));
    float best = 1e9;
    int R = 4000 / n + 20;
    for (int r = 0; r < 5; r++) {
        CK(cuEventRecord(a, s)); for (int i = 0; i < R; i++) CK(cuGraphLaunch(ge, s)); CK(cuEventRecord(b, s)); CK(cuEventSynchronize(b));
        float ms; CK(cuEventElapsedTime(&ms, a, b)); ms /= R; if (ms < best) best = ms;
    }
    printf("n=%d grid=%d block=%d samep=%d best %.1f us  %.2f us/launch\n", n, grid, block, samep, best * 1e3, best * 1e3 / n);
    return 0;
}
