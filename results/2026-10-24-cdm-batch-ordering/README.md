# Cached batched dispatch ordering

M2 Max, Asahi Linux, 2026-10-24. ZLUDA `4db02c1` fixes ordering in the
existing opt-in graph batching path. Separate firmware commands are ordered;
dispatches within one command need the CDM barrier even when shader code
is cached. The old cache-generation check could omit that barrier. Batched
dispatches now always emit it. No unknown command bits were varied.

The earlier Qwen counting failure (repeated `G` tokens) no longer reproduces
with `ZLUDA_AGX_GRAPH_BATCH=1`. Counting, arithmetic, weekdays and an ocean
sentence all match the same llama-app executable's CPU output and exit 0.
See `counting-correctness.json` and `batched-correctness.json`.

## Dependency stress check

`tests/cdm_batch.ptx` is an authored integer dependency probe with `inc`
and `twice` kernels. `agx_runtime`'s `agx_cdm_batch` runner checks 64 dependent
increments in separate commands and one combined command, then an
`inc -> twice` data dependency. It now asserts that every batched dispatch
has a CDM barrier; this catches the original omission even if a simple
execution happens to schedule in order.

Three runs over 65,536 elements each have zero incorrect separate, batched
or chained outputs and exactly 64 batched barriers. Firmware time medians
are 1,808.8 µs separate and 453.5 µs batched; host time medians are 2,519.8
and 51.3 µs. These are fixed-order microbenchmarks, not application speedups
or clock-controlled estimates. Raw rows: `cdm-batch-hardware.json`.

Reproduce:

```bash
python3 scripts/verify_cdm_batch.py \
  --zoc /scratch/geekbench-extract/cargo-target/release/zoc \
  --runner /scratch/geekbench-extract/cargo-target/release/agx_cdm_batch
```

The script compiles the authored PTX, checks all outputs and the barrier
count, and prints the measured rows. The relevant ZLUDA tests pass 47
runtime cases and 33 driver cases.

## Application tradeoff

Four alternating warm Qwen benchmark commands (`off, on, on, off`), each
with three repetitions, use b11706, the supplied Q5_K_M model, CUDA0,
`-ngl 99 -fa off -b 8 -ub 8 -p 128 -n 32 -r 3 -t 4 --no-warmup`.
Median per-command mean throughput:

| Mode | pp128 tokens/s | tg32 tokens/s |
| --- | ---: | ---: |
| Separate commands | 87.85 | 29.78 |
| Ordered batching | 95.68 | 27.74 |

Prompt throughput improves about 9%, while generation drops about 7%.
Total command wall time is nearly unchanged. All runs exit 0. Raw rows:
`llama-batching.json`. Batching therefore remains **off by default**; it is
not a universal application speedup. `/scratch/run-llama-agx` defaults to
off and now honors an explicit `ZLUDA_AGX_GRAPH_BATCH=1` override.

Geekbench off/on runs with existing caches reach all eleven workloads and
then fail the network upload. Both have the same 11 resource-limit tuning
rejections and no other reported CUDA errors. See `geekbench-batching.json`:

| Mode | Wall seconds | Graph calls | Graph host seconds | Sync host seconds | Compiler invocations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Separate commands | 134.572 | 8,770 | 12.866 | 29.331 | 279 |
| Ordered batching | 134.175 | 8,770 | 6.486 | 35.010 | 196 |

Graph host time is halved, but more time appears in synchronization and
total runtime is nearly unchanged. Additional cache misses differ between
the runs, so this is not a fully cache-isolated comparison. It establishes
neither an overall Geekbench speedup nor an independent numerical check of
every workload. The blocked upload cannot supply a published score.

The executable `scripts/verify_cdm_batch.py` was also run separately: its
three cases have zero wrong outputs and exactly 64 barriers each. These
additional rows are in `cdm-batch-script.json`.

The functional simulator operates on shader dispatches and explicit queue
dependencies, rather than CDM packet streams. This fix adds no shader ISA
form or decoder rule. The shader cost model does not parse CDM packets or predict host
submission overhead, so these command-level timing measurements must not
be substituted for shader-cost parameters.
