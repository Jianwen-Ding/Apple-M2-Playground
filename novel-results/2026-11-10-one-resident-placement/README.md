# With one resident workgroup per core, a grid fills only 34 cores per round: 35-40 workgroups take two rounds (memory- or size-limited alike)

Status: confirmed on one device (M2 Max G14C, 38 GPU cores), 2026-11-10, our own probe kernel through agx_runtime
(agx_run_hw `--back-to-back 1000`, firmware times at the top clock). Nothing disassembled or decompiled.

## Test

A fixed-work kernel (each workgroup of 128 threads runs the same straight-line iadd loop, ~88 us alone) given 40000
bytes of threadgroup memory, so that only one workgroup fits a core at a time, launched with 1 to 77 workgroups.

## Result

| workgroups | 1 | 19 | 30 | 34 | 35 | 36 | 37 | 38 | 39 | 40 | 70 | 71 | 72 | 76 | 77 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| us | 87.8 | 88.2 | 87.7 | 88.3 | 167.4 | 167.4 | 167.6 | 167.5 | 167.5 | 167.6 | 247.1 | 247.1 | 246.9 | 247.2 | 247.0 |

- Up to 34 workgroups run in one round; 35 already need a second (one core runs two in a row), 70 a third: the
  busiest core gets ceil(n / 34) workgroups, not ceil(n / 38), and not the even cluster split (ceil(ceil(n/4)/9),
  which predicts one round up to 36).
- The second and third rounds cost ~80 us each (the workgroup's own time): no overlap between a core's rounds.
- The same for workgroups that are alone on a core because of their size (1024 threads, no threadgroup memory,
  `place3.sh`): 1 / 34 workgroups 159 / 162 us, 35 / 38 / 39 workgroups 305-307 us.
- Which 4 cores sit out is not known (the probe does not record the core id), nor whether large grids (hundreds of
  rounds) also leave 4 cores out: Halide's conv_layer relu (1280 x 1024 threads) fits n / 38 rounds better.

## Implications

- Kernels with large threadgroup allocations (llama.cpp's MMQ: 57856 bytes, 38 stream-k workgroups; flash
  attention) pay a whole extra round when the grid exceeds 34 workgroups: a 38-workgroup grid of equal workgroups
  takes ~2x a 34-workgroup one. Sizing such grids to 34 (or a multiple) would avoid it.
- The AGX Performance Simulator uses ceil(n / 34) for one-resident grids since 2026-11-10 (`busiest_core_wgs_resident`).

## Reproduce

`results/2026-11-10-one-resident-placement/place.sh`, `place2.sh` (the probe kernel is
AGX-Performance-Simulator `scripts/probe_fetch_groups.py`'s program with BODY_KB=4: `program(4)`), raw output
`hardware.txt`. The 20000-byte rows (three resident) are in the raw output but not interpreted.
