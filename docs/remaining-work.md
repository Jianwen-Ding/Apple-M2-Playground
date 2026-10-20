# Task 1: remaining work, safe and unsafe (2026-10-17)

> **fp32 IEEE update 2026-10-20:** [exact non-`.ftz` add/mul/fma and `.rz/.rm/.rp` fp32](../novel-results/2026-10-20-fp32-ieee/README.md)
> (`make verify-fp32-ieee`): a soft fma (all modes) and a hybrid native+check path are bit-exact on 21,024 edge/random lanes; the hybrid costs ~15x
> native on subnormal-free data. **div.rn.f32 done** ([fdiv32](../novel-results/2026-10-20-fdiv32/README.md), `make verify-fdiv32`). **sqrt.rn.f32 done** ([fsqrt32](../novel-results/2026-10-20-fsqrt32/README.md)). **rcp.rn.f32 done** (3 ops, exhaustive on hardware; fdiv32 finding). Layout follow-up: a taken `jmp_exec_none` costs ~14 fma at full occupancy; out-of-line slow paths make the exact fma 1.75x faster. Open: apply the layout to div/sqrt, model the taken-branch cost in cost.rs.

> **Shuffle update 2026-10-20:** [cost measured](../novel-results/2026-10-20-shfl-cost/README.md) (`make verify-shfl-cost`): native ~2x a dependent iadd,
> the generic sequence ~18x native; warp-uniform runtime offsets are exact as `and b,31` + native op. Still open: divergent rendezvous, partial
> physical launches, cost.rs wiring, and the threadgroup-barrier gap bits 8-15 with several SIMD groups (a possible named-barrier field;
> deadlock risk, so it needs owner approval).

> **Texture update 2026-10-20 (safe-05):** [3D, 2D-array, cube and buffer targets measured, plus filter precision](../novel-results/2026-10-20-texture-targets/README.md)
> (`make verify-texture-targets`, 35/35): weights round to 1/256; the lod is fp16 with a 1/64 level weight; trilinear is rounded once to
> the 12-bit grid, which corrects the 2026-10-19 "float32-exact" row. Simulator `texture.rs` was updated to match. Follow-ups: wide buffers,
> mipmapped arrays and seamless cube filtering are confirmed. Still open: the 3D 8-tap near-tie residual, cube arrays, cube corners.

> **Alias update, 2026-10-20:** `call r1` writes the link, preserves the original
> issue-active mask and falls through. [22 exact cases](../novel-results/2026-10-20-call-r1/README.md)
> correct the earlier consume-before-write assumption. Simulator `d66f359` and
> `make verify-control-model` now replay all 408 recorded cases exactly. More
> than two target addresses, scattered/empty aliases and the stop/return state
> are the next control gaps.

> **Later 2026-10-20:** suffix and scattered-mask call/return winner rules plus
> all-issue-active call links are measured and integrated into the simulator:
> [386 exact hardware replays](../results/2026-10-20-control-simulator/README.md),
> `make verify-control-model`. The six independent stop counterexamples remain
> open. Next control probes: source/link register aliases, more target addresses,
> deeper/nested divergence and the extra return state behind the stop difference.

> **Update 2026-10-20 (owner-authorized unsafe probing):** isolated empty/partial-mask
> stops and return context now measured: [finding](../novel-results/2026-10-20-empty-stop/README.md),
> `make verify-empty-stop`. 17 variants / 51 dispatches, zero faults, exact recovery controls.
> The old depth-1-kill heuristic holds after return but fails for conditional-only
> masks; six simulator counterexamples retained. Qualified simulator semantics,
> additional return state and broader mask shapes remain open.

> **Loop status 2026-10-19:** autonomous safe pass completed T1 (fence model verified, no change),
> T2 (memory_ordering property 8/8), T3 (fix-up cost ~200ns fetch-bound, no model change), T4 (coverage report
> 2670/2681, 0 mismatches; 20/20 properties), T6a (OOB=0, gather rule, sRGB-12bit), T6b (borders), T6c (16-bit formats),
> T6d (LOD/grad: ceil(lod-0.5), trilinear float32-exact), T6-mapping, T7a (fp64 compares, 18 ops exact).
> Still open (safe): 3D/array targets, texture-unit simulator model, fp64 rounding modes for
> add/mul (div/sqrt/rcp/cvt all modes done 2026-10-19: [fp64-divsqrt](../novel-results/2026-10-19-fp64-divsqrt/README.md),
> shuffle
> partial physical launches / divergent rendezvous / cost (converged sparse masks and paired 64-bit values done 2026-10-20), stack via Mesa, 64-bit atomic decode, safe-02/03 cost-model gaps, skip-conditions analysis.
> Blocked on owner approval: divergent call/ret + atomic-field follow-ups, all `may_fault`/hang-risk sweeps,
> and the outward-facing bfeil upstream report.

> **Update 2026-10-19:** safe-10 memory-ordering litmus is now complete: the minimal SB fence
> set is measured ([f533+f59a for normal stores, +f596 for coherent](../novel-results/2026-10-19-sb-minimal-set/README.md),
> `make verify-sb-minimal`) and multi-group fence contention is measured (wall cost ~group-count
> independent, no serialization: [finding](../novel-results/2026-10-19-fence-contention/README.md),
> `make verify-fence-contention`). Open: a `cost.rs` change to charge device fences once per core
> instead of per group (recorded, not applied: no Rust toolchain in this environment to re-run
> `verify-cost-model`), and the `memory_ordering` coverage case type (wired 2026-10-19:
> `verify-sb-minimal` / `verify-fence-contention` added to the property check, 8/8 pass).
>
> **Update 2026-10-19 (later):** the per-core fence question is settled with no code change:
> `agx_cost` predicts identical per-fence wall costs at 1 and 8 groups (ratio 1.000 in all
> tested cells), matching the contention finding — the event-driven model already combines
> per-group fence stalls with a max, so uniform multi-group fenced code predicts correctly.
> A ratio regression check is now part of `make verify-fence-model`. The Rust toolchain is
> installed in this environment now (`cargo` plus built `agx_run`/`agx_cost`/`agx_predict`/
> `verify_cost_model`), so the remaining coverage-case work is unblocked. Still open: the
> `memory_ordering` coverage case type.

> **Update, later on 2026-10-17 (owner-approved unsafe session):**
> - **Done:** the `while_*` loops (24 guarded and 9 terminating forms, 0 faults; the old "faults" were test design
>   plus a cascade) and the 11 register-base atomics with return.
> - **Done:** device atomic ops 11-15 (they end the SIMD group) and bits 45-46 (float32 atomic add,
>   64-bit unsigned min / max): [finding](../novel-results/2026-10-17-atomic-variants/README.md).
> - The 64-bit atomic gap is now narrower: there is no 64-bit add / CAS / exch in that field.

A single list of what is still open in Task 1 (AGX hardware probing), split by GPU risk. It consolidates the
AGX-Performance-Simulator task files (`tasks/safe-*.md`, `tasks/agx-coverage.md`), the coverage catalog, the
[ISA coverage table](isa-coverage.md) and [failed approaches](../notes/failed-approaches.md).

**State at writing:** both repositories clean and pushed; fresh boot, hang budget 0 / 30 used; AC power.
Coverage: every `safe` case is recorded (3,255; 0 pending). 866 cases are `may_fault`; 214 geometry and 403
undecoded were recorded cleanly, and 6 `while_*` control cases faulted.

**Safe** means: only encodings already run cleanly on this GPU, bounded code gated in `agx_run`, whole programs from
`build_main()`, and the direct-DRM or Vulkan harness. The rules are in AGX-Performance-Simulator `tasks/safe-probes.md`.
**Unsafe** means a GPU hang, a device wedge or data leakage is possible. Each needs the owner's approval, a fresh hang
budget, and ideally a reboot afterwards.

## Safe work

### Open safe tasks, in priority order for CUDA

| # | Work | Task | Why it matters for PTX translation | Status |
|---|---|---|---|---|
| 1 | ~~Memory-ordering litmus tests~~ done 2026-10-18 (safe-10): [SB/LB](../novel-results/2026-10-18-sb-lb/README.md), [atomic release](../novel-results/2026-10-18-atomic-release/README.md), [across dispatches](../novel-results/2026-10-18-dispatch-visibility/README.md), [fence cost](../novel-results/2026-10-18-fence-cost/README.md), [threadgroup](../novel-results/2026-10-18-tg-litmus/README.md). Done 2026-10-18: fence costs in `cost.rs` (`make verify-fence-model`). Done 2026-10-19: [minimal SB fence set](../novel-results/2026-10-19-sb-minimal-set/README.md) (f533+f59a normal, +f596 coherent; `make verify-sb-minimal`) and [multi-group contention](../novel-results/2026-10-19-fence-contention/README.md) (wall cost group-count independent; `make verify-fence-contention`); model needs no per-core change (1-vs-8 ratio 1.000, regression-checked in `verify-fence-model`). Open: the `memory_ordering` coverage case type | safe-10 | Mapping of `fence` / `membar` / `ld.acquire` / `st.release` / `atom.release`. Correctness-critical | MP, SB, LB, atomics, tg, dispatch boundary, cost, minimal SB set, contention measured, model verified |
| 2 | ~~Non-ftz fix-ups for `setp` and `min`/`max` on subnormals~~ correctness done 2026-10-19: [NaN-accepting variants, float-result `set`, fp16 direct mapping](../novel-results/2026-10-19-setp-extra/README.md) (`make verify-fcmp-extra verify-fcmp16`); [fix-up cost](../novel-results/2026-10-19-fixup-cost/README.md): ~200 ns wall (fetch-bound), no model change (`make verify-fixup-cost`); the 2026-10-18 integer-key fix-up covers the base relations. Open: compiler skip conditions (no hardware needed) | safe-01 (open part) | Default (non-`.ftz`) PTX float compares must be bit exact | Conversions and float edges done |
| 3 | ~~In-shader clock~~ done 2026-10-18: [cost under load, per-core copies, skew bound](../novel-results/2026-10-18-clock-load/README.md); the cost-model op is done (`cost::clock_read_ns`) | safe-11 §3 | `clock()`, `clock64()`, `%globaltimer`. No hardware shader clock exists, so this is the only path | Basic read works (0.4-0.75 µs) |
| 4 | ~~Occupancy~~ done 2026-10-18: [~55 workgroup slots, shape-independent, combined limits](../novel-results/2026-10-18-occupancy/README.md); the coverage cases remain | safe-11 §1 | `cudaOccupancyMaxActiveBlocksPerMultiprocessor`, launch tuning | Formula known for the common case |
| 5 | ~~Preshader~~ done 2026-10-18: [uniform file = 32 per CDM group (max 7 groups = 224), one run per core per dispatch, cost](../novel-results/2026-10-18-preshader/README.md); open: coverage case, field 0 | safe-09 | Hoisting kernel-uniform values (`blockDim` products, argument pointers) | Execution model known |
| 6 | fmadd lane-offset: ~~write-to-read distance, inactive source lanes, simulator model~~ done ([2026-10-18](../novel-results/2026-10-18-fmadd-followups/README.md)); bit-52 rule resolved ([pow fixup](../novel-results/2026-10-18-fma-b52/README.md)); coverage cases for lane form and bit 52 recorded | safe-07 | A lane-shifted fma can replace `shfl.up` + `fma` in scans and stencils | Encodings found on 2026-10-11 |
| 7 | Cost-model gaps: per-line serialisation of colliding atomic lanes, strided access, barrier after ALU, store write-back, PTX-compliant sin/cos cost | safe-02 steps 1 (rest) - 5 | Performance stage (stage 4) and kernel-time prediction | Step 1 done; step 5 (sin/cos) done 2026-10-18; step 3 (barrier after ALU) measured 2026-10-18: [the model's shortfall is the dependent-iadd chain rate (3-4x low), not the barrier](../novel-results/2026-10-18-barrier-cost/README.md); `cost.rs` not changed |
| 8 | ~~SLC capacity by bandwidth~~ done 2026-10-18: [about 21 MiB effective, smooth 14-30 MiB, CPU-independent](../novel-results/2026-10-18-slc/README.md) | safe-03 (open part) | Cache-aware lowering and blocking | Latency could not separate the SLC |
| 9 | Textures and images through Mesa-compiled GLSL: encodings, filtering precision, unorm/snorm/sRGB rounding, borders, out-of-range coordinates, simulator model | safe-05 | `tex*`, `tld4`, `surf*` | 2026-10-18 base done; 2026-10-19: [OOB fetch = 0, gather footprint rule, sRGB bilinear 12-bit end to end](../novel-results/2026-10-19-texture-edge/README.md) (`make verify-texture-edge`); plus borders (float quantizes to format, integer exact), 16-bit formats exact, and LOD/gradient (level = ceil(lod-0.5), trilinear float32-exact, grad lod = log2(rho)). 3D/array/cube/buffer targets done 2026-10-20 ([targets](../novel-results/2026-10-20-texture-targets/README.md)); integer formats cannot be filtered in GL. Still open: 3D 8-tap near-tie residual, cube arrays. Simulator model done 2026-10-19 ([texture unit](../novel-results/2026-10-19-texture-unit/README.md), `make verify-texture-unit`); CUDA mapping table updated. Never hand-encode texture state |
| 10 | ~~Imageblock layouts and threadgroup-memory capacity~~ done 2026-10-18: [no effect on occupancy](../novel-results/2026-10-18-imageblock-occupancy/README.md) | safe-11 §2 | Whether tile memory shares the 64 KiB per core | SR12/13/15 identified |

### Gaps not yet covered by any task (safe to start)

- **fp64** (done 2026-10-18: [bit-exact software add / mul / fma, with costs](../novel-results/2026-10-18-fp64/README.md); done 2026-10-19: [all 18 setp / min / max / .u / set forms](../novel-results/2026-10-19-fp64-cmp/README.md) (`make verify-fcmp64`); open: other rounding modes for add/mul; done 2026-10-19: [div/sqrt/rcp/cvt, all PTX rounding modes](../novel-results/2026-10-19-fp64-divsqrt/README.md) (`make verify-fp64-divsqrt`). Original gap: AGX has no fp64 unit, and no finding documents that or measures it. CUDA `double` needs software
  emulation from recorded int64 and fp32 forms. Measure the cost of a double-precision add/mul/fma sequence built only
  from safe forms, and check it bit-exact against IEEE on edge cases.
- **64-bit atomics** (done 2026-10-18: [Honeykrisp exposes none; emulated add measured, final exact, returned value torn across the carry](../novel-results/2026-10-18-atom64/README.md); open: lock-based CAS / exchange, which needs a spin loop and the owner's approval) (`atom.add.u64`, `atom.cas.b64`, `atom.exch.b64`). No validated encoding is known. Device and
  threadgroup ops 11-15 stop the issuing group in the tested forms. Compile a Vulkan shader with
  `GL_EXT_shader_atomic_int64` (if exposed), export the binary and decode Mesa's lowering.
- **Warp shuffle completeness** (done 2026-10-18: [exact lowerings, quad-granular index](../novel-results/2026-10-18-shfl/README.md); 2026-10-20: [converged sparse masks and paired 64-bit payloads](../novel-results/2026-10-20-shfl-mask/README.md) measured; generic index initialization before divergence is required (`make verify-shfl-mask`). Open: partial physical launches, divergent rendezvous, 16-bit forms, cost). Original task: Check that every `shfl.sync` mode (`up`, `down`, `bfly`, `idx`) with `c`-clamp and
  segment-mask operands has a recorded AGX lowering with exact out-of-range behaviour. The cross-lane width finding
  covers reductions and scans, not every shuffle form.
- **Stack / scratch through Mesa only** (done 2026-10-18: [spills, vec4, 16-bit; simulator replay exact](../novel-results/2026-10-18-stack-mesa/README.md); open: `stack_get_ptr`, async forms, the coverage case, spill cost: [rough, 20-43 ALU instructions per pair](../novel-results/2026-10-18-spill-cost/README.md)). Original task: Capture a Mesa shader that spills (`stack-via-mesa`) and record the
  `stack_*` encodings as coverage cases, without hand-built helper programs (`MANUAL` item `stack`). CUDA local arrays
  and register spills depend on it.

### Coverage-suite housekeeping (offline or safe)

- (Done 2026-10-18: fmadd lane-offset cases recorded in the catalog; the other items are covered by `coverage.py properties` in AGX-Performance-Simulator, now 20 verifiers including `verify-sb-minimal` and `verify-fence-contention` under `memory_ordering`.)
- (Done 2026-10-19: [coverage report](../AGX-Performance-Simulator/results/2026-10-19-coverage/README.md): 2670/2681 pass, 0 mismatches; 11 unsupported-by-design (SR21 x10 needs VM context, SR113 time-varying); 5 timing rows >10% off (2 ballot, 2 discard-select, 1 simd_min-f — flagged for safe-02); 0 nondeterministic; 20/20 properties pass.)
- Report the `bfeil` verdict A upstream: Mesa's `fuse_ubfe` is unsound for variable shifts (m2-run-checklist Q1,
  with `viterbifix` as the workaround). This is outward-facing, so it needs the owner's go-ahead.

## Unsafe work (owner approval required)

Each item below either hung the GPU, wedged the device, or has no evidence that it is safe. Run them one at a time
after a reboot, check `gpu_safety.py status` between runs, and stop at the first fault. The device previously wedged
after about 44 recoveries in one boot.

### Needed for CUDA (worth the risk, with care)

> **Update 2026-10-19 (owner-approved unsafe loop, continued):** second item done — all 10 pairs of the inert device-atomic gap bits (26/28/42/43/44) change nothing ([finding](../novel-results/2026-10-19-atomic-pairs/README.md), `make verify-atomic-pairs`): 30 dispatches, 0 faults, budget 0/30, every recovery exact. The u-field is padding singly and pairwise. Not run: triples, pairs with bit 29/31, threadgroup-atomic bit combinations.

> **Update 2026-10-19 (owner-approved unsafe loop):** first item done — cross-group effect of the ending opcodes measured: [op 11 ends the whole workgroup](../novel-results/2026-10-19-tg-end-scope/README.md) (v1 128 lanes + v2 1024 lanes with explicit group-1 re-assertion; `make verify-tg-end-scope`). No fault, budget 0/30, recovery exact. Unsafe submissions pause here for the turn; next candidates: remaining atomic-field combinations, scratch helper, 251 non-Mesa barriers (not needed: safe-10 sufficed), convert/funop/sub-op sweeps, load/store format combos.

| Work | Pending cases | Risk | CUDA need |
|---|---|---|---|
| ~~`while_icmp` / `while_fcmp` loop forms~~ | done 2026-10-17: 24 guarded + 9 terminating recorded; the other 7 never exit by design | none (the hang was the test loop) | Data-dependent loops: every condition code matches the simulator |
| `call` / `ret` | uniform direct/indirect and nested round trips measured; divergence still open: see "Function calls" below | Bad target hangs the GPU | Non-inlined device functions, recursion. Avoidable by inlining everything |
| Direct-DRM scratch / helper program (`async_load`, `async_store`, `stack_get_ptr`, `stack_adjust`, `pop_exec2`) | MANUAL `stack` | Two attempts stalled ~0.5 s | Local memory, spills, `alloca`. Try the Mesa-capture route first (safe list) |
| ~~Device atomic ops 11-15~~ and the remaining gap bits u1-u4 | done 2026-10-17 for ops 11-15 and bits 45-46 | ops 11-15 end the SIMD group, no fault | Float add and u64 min / max found; u1-u4 single-bit follow-up recorded below; combinations and threadgroup atomic bits still open |
| ~~Atomics with return through a register base~~ | done 2026-10-17 (11/11 exact) | none | `atomicAdd` return values with computed addresses |
| `memory_barrier a, b, c` (the 251 non-Mesa encodings) | 251 | Unknown | Possibly cheaper or scope-specific fences. Not needed if safe-10 shows the 7 Mesa encodings suffice |

### Mainly ISA completeness (low CUDA value)

| Work | Pending cases | Risk |
|---|---|---|
| `convert` mode 2, 3, 12+ and round field > 1 | 176 | Confirmed GPU hangs in this family |
| funop functions 2, 3, 5, 7, 11, 15 (`floor` b28_6 space) | 53 | 24 confirmed GPU hangs |
| Other sub-op spaces: `bitrev`, `simd_iadd` gap bits, compare/ballot/select cc values outside the known range | 63 | Unknown sub-ops |
| Device load/store format and addressing combinations outside the safe set (e.g. `rgb10a2`) | 228 | `may_fault` |
| Threadgroup load/store packed formats (`f16`, `rgb10a2`, `u8norm`, `s8norm` with mask and immediate) | 60 | `may_fault` |
| `jmp_incomplete`, `jmp_if_skipping_doorbell` | descriptor only | May loop on itself |
| The 9 dispatch-discarding undecoded opcodes (0x06, 0x24, 0x34, 0x44, 0x46, 0x54, 0x5c, 0x64, 0x74) and the bit-7 forms 0xa8, 0xb8, 0xc8, 0xd8 | n/a | 0x5c wedged the device |
| Ending opcode combined with a barrier in another SIMD group | n/a | Deadlock |
| 256 declared register halves (launch field wraps to 0) | n/a | Result of a wrapped register count unknown |

### Do not run

- **`0x6e` stale-data forms:** on-chip data leakage (the LeftoverLocals class). It is a security issue, not a
  probing target. If it is ever studied, do it only on an isolated machine with the owner's explicit approval.

### Out of reach from compute (needs a render pipeline)

`wait_pix`, `signal_pix`, `ld/st_tile`, `iter`, `iterproj`, `ldcf`, `st_var`, `st_var_final`, `image_write_block`,
`sample_mask`, `zs_emit`. These are fragment-stage instructions with no CUDA use; leave them unless a render path is
built through Mesa.

## Suggested order

1. safe-10 litmus and model are complete (2026-10-19: minimal SB set f533+f59a[+f596], no
   multi-group contention, model verified with no change). Still open in safe-10: the
   `memory_ordering` coverage case type.
2. safe-01 open part, then the fp64 and 64-bit atomic gaps (decode Mesa's int64 atomics if exposed).
3. safe-11 (occupancy, clock) and safe-09 (preshader), the runtime-facing numbers.
4. Stack via Mesa capture, then safe-07 and safe-05.
5. safe-02 / safe-03 performance gaps (needed for stage 4 rather than stage 3).
6. Owner-authorized unsafe follow-ups: divergent call/return and remaining atomic-field combinations.
   Opcode 11-15 and register-base first passes are complete. Continue past logged recovered faults only after
   a passing control; stop further submissions on persistent unresponsiveness.

## Function calls (`call`, `ret`): uniform round trips measured, 2026-10-17

For remaining probes and independent simulator work, use the current
[call/return agent handoff](../notes/call-return-handoff.md). It specifies
dependencies, target/path gates, hardware ownership and fault/hang handling.

- Direct six-byte and register-indirect two-byte calls use buffer-relative byte
  links. The link points just after the instruction (+6 or +2).
- `ret` consumes that buffer-relative link and leaves active lanes at mask depth
  2: the continuation needs `pop_exec r0l, 2`. Direct, indirect and two nested
  direct calls now run with exact markers on all 32 lanes.
- The simulator's opt-in `AGX_EXPERIMENTAL_RET=buffer-pop2` matches all seven
  successful in-program follow-up recordings. Default rejection remains for
  return/indirect-call paths; partial/divergent targets are not yet validated.
- Out-of-program quiet completions are explicitly unmodelled. The old
  code-relative model was wrong; subtracting 0x2000 from the link is not the fix.
- Reports, exact binaries, fault logs and recovery controls are preserved in the
  [call/return finding](../novel-results/2026-10-17-call-ret/README.md).
  `make verify-call-ret` reconstructs the probes and checks their evidence offline.
- Owner clarification: log and push faults; continue after a passing known-good
  recovery control. Stop if recovery is not established. The follow-up ret/no-pop
  and atomic-bit-31 faults both recovered. Current recorded boot budget: 3/30.
- Next: partial active masks, divergent indirect targets, return-mask behavior
  outside the uniform case, and calibrated call/return cost.

## Device atomic gap bits: first follow-up complete

Bits 26, 28, 42, 43 and 44 individually flipped matched the tested integer-add
baseline. Bit 29 returned zero and left memory unchanged for add, exchange and
compare/exchange. Bit 31 caused a recovered unmapped UL1C fault. These are
single-program observations, not general inert-bit or cache-scope claims.
[Finding and verifier](../novel-results/2026-10-17-atomic-gap-bits/README.md).

## Threadgroup atomic follow-up complete for 27 variants

Ops 11-15 stop the issuing group with full, odd-lane and empty masks. An empty
group that jumps over op 11 continues. Selected constant-bit flips and pairs
match integer sub/CAS, with all 2 KiB checked. Bit 15 changes instruction length
and was rejected by the offline layout gate before hardware submission.
No new faults or hangs; budget remains 3/30. Other-group effects and shared
memory after an ending opcode remain open, as do short forms and other bit
combinations. [Finding](../novel-results/2026-10-17-tg-atomic-followup/README.md),
`make verify-tg-atomic-followup`. Future hang diagnostics and bounded
unified-memory trigger investigations are prepared in
[this procedure](../notes/hang-memory-followup.md).

- Textures (safe-05), partial 2026-10-18 ([CUDA mapping table](cuda-texture-mapping.md) written): [conversion, filtering and wrap rules measured](../novel-results/2026-10-18-gles-texture/README.md); 2026-10-19: [simulator model](../novel-results/2026-10-19-texture-unit/README.md) (`make verify-texture-unit`) with store rounding and PBE; still open: 1D/3D/array targets, integer filtering formats.

- PTX-compliant sin/cos cost (safe-02 item 5), done 2026-10-18: [fma-split costs the same as Mesa's sequence](../novel-results/2026-10-18-sincos-cost/README.md).

## 2026-10-20 call/return and execution-mask update

Lowest-active target selection, issue-active link writes, three-target and
scattered masks, and call-r1 write-before-select ordering are now measured.
Nonempty return maps low counters `0 -> 2, 1 -> 0, deeper unchanged` through
depth 4; empty-issued return falls through unchanged. Stop ends issuing lanes
while masked survivors continue. Simulator defc29d incorporates the later
conditional stored-depth RET and native shuffle liveness corrections;
all 2,403 retained original programs now replay exactly.

[Masked-r0 shuffles](../novel-results/2026-10-20-masked-r0/README.md) directly
read initialized low counters from masked lanes and corroborate the return
map. [Stopped-source follow-ups](../novel-results/2026-10-20-dead-index-or/README.md)
now distinguish terminated from masked lanes: stopped sources self-fallback
and their index bits no longer contribute to the quad OR. Their underlying
register storage remains unobserved. Remaining questions include deeper
counters, quad shuffle and other cross-lane termination effects,
nested divergent composition and calibrated control-flow costs. The current
probe boot has zero recorded faults; earlier boot budgets above are historical.

The four relative/xor/rotate native shuffle forms now separately reproduce
stopped-source fallback and exclusion of stopped low-index bits. Their 480
programs and 1,440 dispatches completed with exact controls, no faults.
[Native finding](../novel-results/2026-10-20-native-dead-index-or/README.md),
[model integration](../results/2026-10-20-native-shuffle-model/README.md).

[Nested divergent calls](../novel-results/2026-10-20-nested-divergent/README.md):
direct/indirect full-group outer calls with three-way divergent inner calls
complete exact round trips after explicit two-pop reconvergence and saved-link
restoration. Twelve programs / 36 dispatches, exact no-call controls, no faults.
Partial outer masks and fewer inner pops remain separate work.

[Nested early returns](../novel-results/2026-10-20-nested-early-return/README.md):
zero/one inner pop cases follow the same counter transform. One pop makes
inner participants active immediately at the outer landing. Only lanes that
were active during r1 restoration receive the outer link; matching inner
participants retain inner links even at the final full-group marker. Twenty-four
programs / 72 dispatches, exact controls, no faults. Partial original outer
participation remains open.

[Partial outer nesting](../novel-results/2026-10-20-nested-partial-outer/README.md):
144 programs / 432 dispatches show originally excluded depth-1 lanes waking
at inner return with their original r1 ID intact. Every saved transfer link
was explicitly initialized. All cases match the model with exact controls,
no faults. Balanced per-call counter reservation is the next compiler-convention
question; unreserved nested pops do not implicitly preserve the outer mask.

[Balanced call-mask reserve](../novel-results/2026-10-20-call-mask-reserve/README.md):
push_exec 2 before **each** nested call, balanced by its return/pop2, preserves
the enclosing mask at two levels. Either missing reserve allows excluded
lanes at the outer caller. The 192-program / 576-dispatch four-way contrast
reads masked counters 0/3/5 directly and checks preserved r1 IDs. Every word
and recovery control is exact, no faults. Deeper balanced nesting is next.

[Deep balanced reserves](../novel-results/2026-10-20-deep-call-reserve/README.md)
preserve masks/links through 3/4/8 calls with mixed forms and a divergent leaf.
192 programs / 576 dispatches, exact controls and zero faults. Direct excluded
low-counter reads show odd depths 3..17, with two-count restoration at each
matching continuation. Consecutive larger depths remain a separate question.

[Consecutive return counters](../novel-results/2026-10-20-deep-ret-counters/README.md):
direct low-r0 reads confirm nonempty RET maps 0 -> 2, 1 -> 0 and leaves every
consecutive depth 2..31 unchanged. Sixteen programs / 48 dispatches, both lane
rotations and payload controls, every word exact, zero faults. The later ordinary-r0-write matrix below measures execution synchronization.

[Ordinary r0 writes](../novel-results/2026-10-20-r0-write-mask/README.md) update
counter storage but preserve the issuing mask until a dedicated mask operation.
Pop1 then decrements the written counters and updates execution. Thirty-four
programs / 102 dispatches cover four write forms and mixed/uniform depths to 31,
exact controls and zero faults. Zero-count synchronization and larger values
remain next questions; simulator 4dd68e9 already matches.

[Zero-count synchronization](../novel-results/2026-10-20-r0-pop0/README.md):
pop_exec 0 synchronizes the issuing mask after ordinary r0 writes, selecting
only zero counters. Thirty-four programs / 102 dispatches, controls without
pop0, all words exact, zero faults. Numeric masked counters after pop0 and RET
with deliberately stale execution remain follow-ups.

[Stale-execution RET](../novel-results/2026-10-20-ret-stale-exec/README.md)
corrects the cached-issue model: nonempty RET conditionally maps stored counter
0 -> masked 2, 1 -> active 0, leaving deeper counters and execution unchanged.
All 34 hardware counterexamples (102 dispatches, exact controls, zero faults)
now replay in simulator c7e50f7. Uniform nonzero counters still transfer.
Target disagreement in stale execution remains open.

[Wide unsigned counters](../novel-results/2026-10-20-wide-r0/README.md):
36 programs / 108 dispatches, sampled boundaries through 0xffff and both lane
rotations. Pop0 retains numeric values; RET preserves sampled deeper values;
pop1 decrements unsigned with zero saturation. 0xffff remains living/readable
and later rejoins after the bounded drain. Independent payload controls and
all full buffers are exact, zero faults. Recorded AC-online is 0 throughout;
no timing claim. Increment overflow and other mask operations remain open.

[Stale-execution divergent targets](../novel-results/2026-10-20-ret-stale-targets/README.md):
RET chooses the lowest cached issuer before conditional counter updates.
90 programs / 270 dispatches, three destination rotations and five masks,
all words/controls exact, zero faults. Sixty cases differ from zero-counter
selection, 66 updated participation, 36 both. The unchanged model is exact;
already-masked writes and increment overflow remain independent questions.

[Overflow first-shuffle anomaly](../novel-results/2026-10-20-overflow-first-shuffle/README.md):
27 programs / 81 dispatches including the base family, zero faults and exact
controls. Increment overflow reactivates a masked lane, but its first native
shuffle retains the destination value. Wait0/pop0/a second shuffle fixes
the tested program; one ordinary ALU instruction does not. Eighteen current
simulator counterexamples remain explicit, separate from the exact corpus.
Determine masked-destination writes and execution-state update conditions
before implementing a general mask/pipeline rule.

[Prepared-index overflow destinations](../novel-results/2026-10-20-overflow-register-visibility/README.md)
extend the effect to immediate/copy/add and separate it from address ALU.
27 programs / 81 dispatches, exact controls, zero faults. Retained values
persist after wait/drain; spacing and lane-dependent boundaries are recorded
without claiming calibrated cycles. There are now 35 explicit counterexamples
across the two overflow families; the 2,403-program exact corpus is separate.

[Overflow activation guard](../results/2026-10-20-overflow-guard/README.md):
default simulation requires measured wait0/pop0 settlement after masked-lane
IF/push overflow activation. Raw overflow replay accepts 11 exact and refuses
43 unresolved programs, including eight conservatively refused hardware-exact
ones. Explicit counter-sync opt-in retains all 35 old counterexamples. Earlier
2,403 cases remain exact, 44 library tests pass; timing/alignment remain open.
