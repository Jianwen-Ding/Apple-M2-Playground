# llama.cpp's MMQ workgroups run ~30% slower when 34 cores are busy than when 16 are (Q5_K 1645 -> 2146 us), growing as clusters 2 and 3 join

Status: confirmed on one device (M2 Max G14C), 2026-11-10. Kernels: our own clang CUDA -> PTX -> ZLUDA -> AGX compile
of llama.cpp `mul_mat_q<Q5_K / Q6_K>` (pp512, Qwen2.5 0.5B), captured and replayed with agx_run_hw
`--back-to-back 200` at smaller grids. The kernel keeps its captured gridDim (38) for the stream-k split, so a grid
of n runs workgroups 0..n-1 of the 38 with the same work each. One resident workgroup per core (57856 B of
threadgroup memory, 1376 B of stack per thread).

## Result

| workgroups (busy cores) | 8 | 16 | 17 | 24 | 26 | 28 | 32 | 34 | 38 |
|---|---|---|---|---|---|---|---|---|---|
| Q5_K hw us | 1618 | 1645 | 1660 | 1855 | 1912 | 1986 | 2109 | 2146 | 3712 |
| Q6_K hw us | 2412 | | 2693 | | | | | 3260 | 5529 |

- Workgroups are placed in chunks of 8 per cluster ([placement](../2026-11-10-workgroup-placement/README.md)): 8 =
  cluster 0, 16 = clusters 0-1, 24 = 0-2, 32 = all four. Cluster 1 joining costs +27 us, cluster 2 +195, cluster 3
  +254: the slowest workgroup's time grows with the busy cores beyond 16.
- The simulator, with every core simulated, gives every workgroup 1.39-1.56 ms (Q5_K) at any grid: the
  workgroups' own work does not differ enough to explain it.
- Not the bandwidth below L1 for loads: [32 groups per core streaming per-core regions](../2026-11-10-l2-region-streaming/README.md)
  slow by only 7% from 1 to 34 cores at 1.8 TB/s GPU-wide (`265-l2bw` log here). Not clock: an ALU loop on 1-32
  cores is identical ([alu rate](../2026-11-10-alu-issue-rate/README.md)).
- Open: the MMQ kernels' stack traffic (~270k stack-store lines and ~740k stack-load lines per workgroup) is the
  main thing they do that the probes do not; a stack probe the hardware accepts is needed.

## Implications

- Prompt-processing MMQ kernels lose ~25% at full occupancy to an unknown shared resource; the simulator is -22%
  (Q5_K) for this reason.

## Reproducer and evidence

`gsweep.py CAPDIR 512,8,1 768,8,1 ... --hw` on the captures (`/scratch/sim-captures/r5/llama-pp-fa0/*mul_mat_q*type13*`,
`*type14*`). [Evidence](../../results/2026-11-10-mmq-busy-cores/).
