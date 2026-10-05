# Special-register hardware evidence

[Experiment and limits](../../experiments/registers/special-register-scan.md).
Every JSON record preserves the original structured run data, minified without
changing values. Exact original scratch-record hashes and mappings to deduplicated
source snapshots are in `packaging-index.json`. Executables/bulk child files stay
in scratch; every checked readback is retained as exact hex inside the records.

- `full-single.json`: all 256 selectors, three samples, 257 active invocations.
- `full-paired.json`: all 256, three samples, 16 lanes and two reads separated by
  128 native adds, including original and rebuilt constant controls.
- `known-controls.json` / `pair-controls.json`: initial known-selector checks.
- `count-*.json`: fifteen prefix-mask boundary runs, two samples per selector.
- `sparse-even.json`: ten selectors, count 33, three repeats, even indices active.
- `context-{1,33,65,257}.json`: twelve dispatches per child/device, with 10 ms
  requested spacing; new command buffers per iteration. Each has before/after
  constant controls. Count257 includes thirteen selected SRs; smaller counts
  focus on SR32 and SR21.
- `failed-*.json`: local patch validation failures preserved; no mutated shader
  was submitted in those runs. They may contain a successful original control.
- `sources/`: exact original run sources, named by hash; `logs/` retains builds
  and runtime dependency reports.
- `verification.json` and `manifest-sha256.json`: integration verification and
  retained-file integrity. Only successful selected records contribute to totals.

`make verify-sr` verifies all retained buffers and field reconstructions using
only Python's standard library. It imports neither vendor code nor the execution
patcher. It also checks the mathematical lane/population descriptions and the
same-context SR21/SR32 behavior, plus deliberate corruption rejection.
`make check` checks current Python/C syntax without opening the GPU.

The initial single/paired runner source snapshots predate subsequent sparse and
CLI additions. Snapshots are historical evidence; current source is used for
reproduction. No full sweep was repeated merely to refresh source hashes.
