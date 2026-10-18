# Register spills cost roughly 20-60 ALU instructions per spill + fill pair

Status: rough, one device (M2 Max G14C), host-side timing only. Fills the "spill cost" gap of the
[stack-through-Mesa finding](../2026-10-18-stack-mesa/README.md). Mesa GLES compute shader, 0 faults.

## Test

A dependent integer chain keeps NV values live to the end (the `spill` shader of `run_gles_stack2.py`), NV = 16 ... 384, 262,144 lanes, 5 runs.
Mesa's own spill / fill counts come from the captured listing; time is the host-side fence wait (sub-millisecond, so it includes a constant driver
overhead: only differences are meaningful).

## Result

* Mesa spills nothing up to 96 live values; from 128 it spills 6, then 70 / 134 / 262 at 192 / 256 / 384 (fills equal spills). Outputs match the host model.
* Without spills, time is linear in instruction count: **0.23 us per instruction per 262,144 lanes** (fit on 32-96 values).
* Above the fit, one **spill + fill pair costs 7.7 us (192), 4.7 us (256), 10.0 us (384)** per 262,144 lanes: **about 20-43 ALU-instruction
  equivalents** per pair. The 6-spill case is inside the noise.

Caveats: the numbers mix the stack store, the stack load (which waits for the store) and any extra dependency stalls and occupancy change (more private
memory); a 1 ms fence floor and run-to-run noise (up to 30% at 256) limit this to an order of magnitude. Not wired into `cost.rs`: the simulator
still costs `stack_load` / `stack_store` like other memory ops. An in-shader clock probe of a single spill is the way to a tighter number.

## Reproduce

`python3 scripts/run_gles_spillcost.py`; `make verify-spill-cost` (offline, 5 checks against
[results/2026-10-18-spill-cost](../../results/2026-10-18-spill-cost)).
