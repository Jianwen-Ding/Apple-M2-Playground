# Workgroup placement: chunks of 8 consecutive workgroups go to clusters, a cluster's workgroups to its cores round robin (fixed, not first-free)

Status: confirmed on one device (M2 Max G14C, 38 GPU cores), 2026-11-10, our own probe kernel through agx_runtime
(agx_run_hw; firmware times at the top clock, `--back-to-back` 2000-5000). Nothing disassembled or decompiled.

## Test

`AGX-Performance-Simulator/scripts/probe_resident_order.py`: N workgroups of 128 threads; each runs an in-cache iadd
loop (S = 100 trips, ~44 us alone; workgroups in [LONG) run L = 300 trips) and stores its core id (`get_sr sr20`,
`core_index`) at word [workgroup id]. Threadgroup memory 40000 B (one resident per core), 20000 B (three) or none.

## Result

- Core ids are 0-9, 16-24, 32-40 and 48-57: four clusters of 10, 9, 9, 10 cores (ids within a cluster are
  contiguous from a multiple of 16).
- Workgroups are dealt in **chunks of 8 consecutive ids** to clusters. The first chunks always go to clusters
  0, 1, 2, 3, **3**, 0, 1, 2 (cluster 3 takes workgroups 24-39); later chunks in a mostly repeating 1, 0, 2, 3, 0, 1,
  2, 3 order that varies a little between runs (each cluster gets the same number of chunks, whatever its size).
- Inside a cluster the workgroups go to its cores **round robin** in id order (cluster 0: 0-7 for the first chunk,
  then 8, 9, 0, 1, ... for its second), independent of which core is free; only once a cluster is saturated
  (beyond ~3 chunks) does the order within a chunk vary.
- So the first round of a grid uses only 34 cores (8 of clusters 0-2 + all 10 of cluster 3): 35-40 one-resident
  workgroups take two rounds, and at 38 workgroups the extra workgroups 34-37 run on cores 48-51 **after workgroups
  24-27**: with 24-27 long (L) the grid takes L + S (167.8 us); with 0-3 or 30-33 long it takes L (128.3 us).
  Static pairing, not first-free scheduling.
- The same placement with 3 resident workgroups per core (20000 B) and with no threadgroup memory: occupancy does
  not change where the workgroups go (at 38 workgroups, 48-51 get two each).
- Rounds: N = 34: 48.4 us, 38-64: 88 us (two), 72-96: 128 (three), 136: 208 (five: cluster 1 gets 5 chunks = 40
  workgroups on 9 cores), 200: 247.

Raw: `hardware-order1.txt` (first probe, LONG variants), `hardware-order2.txt` (N = 1-200, three occupancies).
N = 9 put all 9 workgroups on cluster 0 (an exception to the chunking not understood).

## Implications

- CUDA grids sized to the core count (llama.cpp's stream-k MMQ uses 38 workgroups of 57856 B threadgroup memory)
  pay a second round on 4 cores of cluster 3: 34 (or a multiple of 8 that fills the clusters evenly) is better.
- AGX Performance Simulator: `dispatch::placement` (per-core workgroup lists) since 2026-11-10.
