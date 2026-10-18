# Cross-core memory ordering: `unknown_barrier_1` (f533) is the release fence; `memory_barrier` alone does not order

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Message-passing litmus with no loops or spin-waits; only Mesa-emitted encodings.

## Claim and scope

Each of 65,536 lanes (32-lane workgroups) stores `data = 1`, a writer fence, `flag = 1`, then
reads a lane in the neighbouring workgroup 16 times: flag, then data (coherent loads). A read
of `flag = 1, data = 0` is a violation. Per variant: 1,048,576 reads, 1–3 repeats.

| Writer fence between the two stores | Violations |
| --- | --- |
| none | 40,000–100,000 per run |
| `memory_barrier` (f596), Mesa's only barrier below queue-family scope | 40,000–90,000 |
| any of f59a, f59e, f503, f599, f59d, alone or after f596 | 35,000–130,000 |
| **`unknown_barrier_1` (f533)**, alone or after f596 | **0** |
| Mesa's queue-family sequence (f596 f533 f59a f59e f503 f599 f59d) | **0** |

With f533 on the writer, the reader still needs an acquire:

| Reader between the flag load and the data load | Violations (3 × 1,048,576 reads) |
| --- | --- |
| `wait 0`, then `device_barrier_1` (f59d) | **0** (both store policies, with or without an f59d before the flag load) |
| f59d before the flag load only | 0 |
| `wait 0` only, no f59d anywhere | 3,328 with normal stores (stale cached data line), 0 with coherent stores |
| both loads issued before one `wait 0` | 96–336 (loads complete out of order) |

* **Pairs whose two lanes ran on the same core never violated** in any variant (SR20 recorded
  per lane); the reordering is between cores.
* Messages become visible mid-dispatch without any fence (the flag was seen in 20–95% of reads).
* Store cache policy (Mesa u4 = 4 or 7) did not matter once the release and acquire are present.

Update 2026-10-18: SB and LB are now measured ([sb-lb finding](../2026-10-18-sb-lb/README.md)): SB across cores needs more
than f533; LB was not observed.

Not established: which of release/acquire the other barriers implement on other memory types,
store→load (SB) and load→store (LB) orderings, the cost of f533, behaviour across
dispatches, and threadgroup-memory ordering.

## Reproducer and evidence

`make test-memory-ordering` (hardware), `make verify-memory-ordering` (offline, 0 failures).
Runner: `scripts/run_drm_litmus.py`. [Evidence](../../results/2026-10-11-memory-ordering/README.md).

## Relationship to existing knowledge

Mesa (`agx_compile.c:1514-1534`) emits only `memory_barrier` for global-memory barriers below
queue-family scope and the seven-barrier "big hammer" only at queue-family scope, with the
comment that it is not clear what the opcodes do; `agx_opcodes.py` calls f533 `unknown_barrier_1`.
The [in-shader clock finding](../2026-10-11-in-shader-clock/README.md) showed f59d/f533 invalidate
for coherent loads. That f533 is the cross-core store release, and that `memory_barrier` alone
does not order stores between cores, are new. If Mesa's device-scope barriers rely on f596 alone,
cross-workgroup message passing at device scope may be unsafe on G14C; this was not tested
through Mesa itself.

## Compiler implications (PTX)

* `st.release.gpu` / `fence.acq_rel.gpu` / `__threadfence()` before the flag store: **f533**.
* `ld.acquire.gpu`: coherent load, `wait`, then **f59d** before later loads of the payload.
* `membar.cta` within one workgroup needs no cross-core fence (same-core pairs never violated);
  threadgroup memory was not tested.
* Never emit only `memory_barrier` for device-scope ordering.
