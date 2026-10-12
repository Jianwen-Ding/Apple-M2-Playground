# Memory-hierarchy evidence (2026-10-11)

`scripts/mem_probes.py`; rows: `kind`, `stride` (words between lanes), `groups`, `window_bytes`,
`private` / `global`, `pad`, `core_cycles_per_step` (reference units per memory instruction of every group),
`mhz`, `stable_cores`. Files: `coalesce-shared.json` (all groups on the same lines), `coalesce-private.json`
(groups 4 KiB apart), `store.json`, `private.json` (per-workgroup windows), `stream.json` (one GPU-wide window,
grid stride; windows ≤ 64 MiB involve reuse across cores), `stream-dram.json` (its ≥ 128 MiB rows), `pad.json`
(ALU after each wait), `inter.json` (private windows, 0/1/2 ALU instructions after every load), `noise-idle.json` / `noise-cpuload.json` (10 busy CPU cores). `make verify-memory-hierarchy`.
