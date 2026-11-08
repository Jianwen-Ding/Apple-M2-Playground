#include <cuda_runtime.h>
#include <stdio.h>
// idx functions with quad-uniform low bits that differ between quads
__host__ __device__ __forceinline__ int idx_of(int f, int lane) {
  int q = lane >> 2, w = lane & 3;
  switch (f) {
  case 0: return (((q * 5) & 7) << 2) | (q & 3);             // permutes quads, position from q
  case 1: return (lane & 28) | ((lane >> 2) & 3);              // own quad, position q&3
  case 2: return ((lane ^ 8) & 28) | ((lane >> 3) & 3);        // other quad
  case 3: return ((q * 3 + w) & 7) * 4 + ((q >> 1) & 3);       // differing quads inside a quad, uniform low bits
  default: return lane;
  }
}
template <int f> __global__ void k(int *out, int n) {
  int lane; asm("mov.u32 %0, %%laneid;" : "=r"(lane));
  int x = lane * 100 + 7;
  int idx = idx_of(f, lane);
  for (int i = 0; i < n; i++) x = __shfl_sync(0xffffffff, x, idx) + 1;
  out[threadIdx.x] = x;
}
int main() {
  int *d; cudaMalloc((void **)&d, 32 * 4);
  int bad = 0;
  for (int f = 0; f < 4; f++)
    for (int n = 1; n <= 3; n++) {
      if (f == 0) k<0><<<1, 32>>>(d, n); else if (f == 1) k<1><<<1, 32>>>(d, n); else if (f == 2) k<2><<<1, 32>>>(d, n); else k<3><<<1, 32>>>(d, n); cudaDeviceSynchronize();
      int h[32]; cudaMemcpy(h, d, 128, cudaMemcpyDeviceToHost);
      int ref[32], tmp[32];
      for (int l = 0; l < 32; l++) ref[l] = l * 100 + 7;
      for (int i = 0; i < n; i++) { for (int l = 0; l < 32; l++) tmp[l] = ref[idx_of(f, l)] + 1; for (int l = 0; l < 32; l++) ref[l] = tmp[l]; }
      int e = 0; for (int l = 0; l < 32; l++) e += h[l] != ref[l];
      // model of one unsplit simd_shuffle: thread r reads quad idx(r) >> 2 at the OR of the low index bits of that
      // quad's own threads
      int mod[32];
      for (int l = 0; l < 32; l++) mod[l] = l * 100 + 7;
      for (int i = 0; i < n; i++) {
        for (int l = 0; l < 32; l++) { int q = idx_of(f, l) >> 2, p = 0; for (int t = 4 * q; t < 4 * q + 4; t++) p |= idx_of(f, t) & 3; tmp[l] = mod[4 * q + p] + 1; }
        for (int l = 0; l < 32; l++) mod[l] = tmp[l];
      }
      int em = 0; for (int l = 0; l < 32; l++) em += h[l] != mod[l];
      printf("f=%d n=%d: %s (%d wrong; %d differ from the source-quad model)", f, n, e ? "FAIL" : "ok", e, em);
      if (e) { printf("  lane:got/want"); for (int l = 0; l < 8; l++) printf(" %d:%d/%d", l, h[l], ref[l]); }
      printf("\n"); bad += e;
    }
  return bad != 0;
}
