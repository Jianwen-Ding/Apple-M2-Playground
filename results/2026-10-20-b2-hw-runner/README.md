# B2: the generic hardware runner on the M2 Max (2026-10-20)

Blocker B2 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: pass, both steps.**

Device: Apple M2 Max (G14C, 38 cores), Asahi kernel 6.19.14-400.asahi.fc42.aarch64+16k, AC power.
Hang budget before and after: 0 / 30 used. cgroup shmem 0 before and after every run (no BO leak).

## Step 1: `agx_run_hw` smoke kernels

ZLUDA branch `claude/bold-davinci-46xi9q` at the commit in `zluda-base-commit.txt`,
`cargo build --release -p agx_runtime` (27 unit tests pass). Each kernel was first run in the simulator's
`agx_run` (same script, `RUNNER=agx_run`): all four outputs PASS there.

```
RUNNER=/scratch/ZLUDA/target/release/agx_run_hw sh tasks/ptx-hw-smoke/run_smoke.sh
== vadd   {"completed":true,"cpu":"agx-g14c","cores":38,"fw_ticks":9916,"fw_ns":9916,"host_us":605}
== ids2d  {"completed":true,"cpu":"agx-g14c","cores":38,"fw_ticks":8750,"fw_ns":8750,"host_us":490}
== tgrev  {"completed":true,"cpu":"agx-g14c","cores":38,"fw_ticks":11459,"fw_ns":11459,"host_us":468}
PASS ids2d.bin
PASS tgrev-count.bin
PASS tgrev.bin
PASS vadd.bin
```

A first lone `vadd` run: `fw_ns` 10417, PASS.

Note: this host has no `cmp` (diffutils); the script was run with a two-line Python stand-in on PATH.

## Step 2: vectorAdd through the CUDA driver API (`agx_cuda_smoke`)

```
target/release/agx_cuda_smoke AGX-Performance-Simulator/tasks/ptx-hw-smoke/cuda/vectoradd_g14c.o
{"device":"Apple M2 Max (G14C, 38 cores)","link_ok":null,"n":50000,"wrong":0,"graph_wrong":0,"unified":true,"unified_wrong":0,"copy2d_wrong":0,"kernel_ms":0.066501}
```

`wrong` 0 = pass; graph, unified-memory and 2D-copy checks also 0 wrong.

## aarch64 build fix needed in ZLUDA

`zluda_agx` did not build on aarch64: `c_char` is `u8` there, and `format/src/lib.rs` implemented
`CudaDisplay` for callbacks taking `*const i8`; `agx_cuda_smoke.rs` used `[0i8; 128]`. The fix
(`zluda-aarch64-c_char.patch`, 3 lines, uses `std::ffi::c_char`) is local to /scratch/ZLUDA and not yet pushed.

## Not answered here

B2a (partial workgroups), B2b (Uniform word size field), B2c (Shared "none" encoding) remain open.
