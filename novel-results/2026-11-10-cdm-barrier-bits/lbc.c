// Ordering/visibility between dispatches of one command: 64 ping-pong dispatches out[t] = in[(t+S)%N] + 1, the graph
// launched R times; every value must end at 64*R. usage: lbc [R] [wgs]
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
typedef int CUresult; typedef void *CUcontext, *CUmodule, *CUfunction, *CUstream, *CUgraph, *CUgraphExec;
typedef uint64_t CUdeviceptr;
CUresult cuInit(unsigned); CUresult cuDevicePrimaryCtxRetain(CUcontext *, int); CUresult cuCtxSetCurrent(CUcontext);
CUresult cuModuleLoadData(CUmodule *, const void *); CUresult cuModuleGetFunction(CUfunction *, CUmodule, const char *);
CUresult cuLaunchKernel(CUfunction, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned, CUstream, void **, void **);
CUresult cuStreamCreate(CUstream *, unsigned); CUresult cuStreamBeginCapture_v2(CUstream, int); CUresult cuStreamEndCapture(CUstream, CUgraph *);
CUresult cuGraphInstantiateWithFlags(CUgraphExec *, CUgraph, unsigned long long); CUresult cuGraphLaunch(CUgraphExec, CUstream);
CUresult cuStreamSynchronize(CUstream); CUresult cuMemAlloc_v2(CUdeviceptr *, size_t); CUresult cuMemsetD32_v2(CUdeviceptr, unsigned, size_t);
CUresult cuMemcpyDtoH_v2(void *, CUdeviceptr, size_t);
#define CK(x) do { int e_ = (x); if (e_) { fprintf(stderr, "%s: %d\n", #x, e_); exit(1); } } while (0)
static const char *ptx =
".version 7.0\n.target sm_80\n.address_size 64\n"
".visible .entry st(.param .u64 a, .param .u64 b, .param .u32 n, .param .u32 s) {\n"
" .reg .u64 %rd<8>; .reg .u32 %r<12>;\n"
" ld.param.u64 %rd1, [a]; ld.param.u64 %rd2, [b]; ld.param.u32 %r1, [n]; ld.param.u32 %r2, [s];\n"
" mov.u32 %r3, %ctaid.x; mov.u32 %r4, %ntid.x; mov.u32 %r5, %tid.x; mad.lo.u32 %r6, %r3, %r4, %r5;\n"
" add.u32 %r7, %r6, %r2; rem.u32 %r7, %r7, %r1;\n"
" cvta.to.global.u64 %rd1, %rd1; cvta.to.global.u64 %rd2, %rd2;\n"
" mul.wide.u32 %rd3, %r7, 4; add.u64 %rd3, %rd1, %rd3; ld.global.u32 %r8, [%rd3]; add.u32 %r8, %r8, 1;\n"
" mul.wide.u32 %rd4, %r6, 4; add.u64 %rd4, %rd2, %rd4; st.global.u32 [%rd4], %r8; ret; }\n";
int main(int argc, char **argv) {
    int R = argc > 1 ? atoi(argv[1]) : 50, wgs = argc > 2 ? atoi(argv[2]) : 152; unsigned n = wgs * 256, S = 4099 * 7;
    CUcontext ctx; CK(cuInit(0)); CK(cuDevicePrimaryCtxRetain(&ctx, 0)); CK(cuCtxSetCurrent(ctx));
    CUmodule m; CK(cuModuleLoadData(&m, ptx)); CUfunction f; CK(cuModuleGetFunction(&f, m, "st"));
    CUstream s; CK(cuStreamCreate(&s, 0)); CUdeviceptr A, B; CK(cuMemAlloc_v2(&A, n * 4)); CK(cuMemAlloc_v2(&B, n * 4));
    CK(cuMemsetD32_v2(A, 0, n)); CK(cuMemsetD32_v2(B, 0, n));
    CUgraph g; CK(cuStreamBeginCapture_v2(s, 0));
    for (int i = 0; i < 64; i++) {
        void *args[] = {i & 1 ? &B : &A, i & 1 ? &A : &B, &n, &S};
        CK(cuLaunchKernel(f, wgs, 1, 1, 256, 1, 1, 0, s, args, 0));
    }
    CK(cuStreamEndCapture(s, &g)); CUgraphExec ge; CK(cuGraphInstantiateWithFlags(&ge, g, 0));
    for (int r = 0; r < R; r++) CK(cuGraphLaunch(ge, s));
    CK(cuStreamSynchronize(s));
    unsigned *h = malloc(n * 4); CK(cuMemcpyDtoH_v2(h, A, n * 4));
    size_t bad = 0; unsigned lo = ~0u; for (unsigned i = 0; i < n; i++) { if (h[i] != 64u * R) bad++; if (h[i] < lo) lo = h[i]; }
    printf("R=%d wgs=%d bad %zu of %u (min %u, want %u)\n", R, wgs, bad, n, lo, 64u * R);
    return bad != 0;
}
