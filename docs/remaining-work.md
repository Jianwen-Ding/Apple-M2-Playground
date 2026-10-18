# Task 1: remaining work, safe and unsafe (2026-10-17)

> **Update 2026-10-18:** the fmadd lane-offset form is decoded and modeled (measured subset, `make verify-fmadd-lane`,
> `make verify-fmadd-decode`); safe-10 (memory ordering) is measured except for the items listed in row 1 below.

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
| 1 | ~~Memory-ordering litmus tests~~ done 2026-10-18 (safe-10): [SB/LB](../novel-results/2026-10-18-sb-lb/README.md), [atomic release](../novel-results/2026-10-18-atomic-release/README.md), [across dispatches](../novel-results/2026-10-18-dispatch-visibility/README.md), [fence cost](../novel-results/2026-10-18-fence-cost/README.md), [threadgroup](../novel-results/2026-10-18-tg-litmus/README.md). Done 2026-10-18: fence costs in `cost.rs` (`make verify-fence-model`). Open: a minimal sufficient SB fence set, multi-group fence contention | safe-10 | Mapping of `fence` / `membar` / `ld.acquire` / `st.release` / `atom.release`. Correctness-critical | MP, SB, LB, atomics, tg, dispatch boundary and cost measured |
| 2 | Non-ftz fix-ups for `setp` and `min`/`max` on subnormals | safe-01 (open part) | Default (non-`.ftz`) PTX float compares must be bit exact | Conversions and float edges done |
| 3 | ~~In-shader clock~~ done 2026-10-18: [cost under load, per-core copies, skew bound](../novel-results/2026-10-18-clock-load/README.md); the cost-model op is done (`cost::clock_read_ns`) | safe-11 §3 | `clock()`, `clock64()`, `%globaltimer`. No hardware shader clock exists, so this is the only path | Basic read works (0.4-0.75 µs) |
| 4 | ~~Occupancy~~ done 2026-10-18: [~55 workgroup slots, shape-independent, combined limits](../novel-results/2026-10-18-occupancy/README.md); the coverage cases remain | safe-11 §1 | `cudaOccupancyMaxActiveBlocksPerMultiprocessor`, launch tuning | Formula known for the common case |
| 5 | ~~Preshader~~ done 2026-10-18: [uniform file = 32 per CDM group (max 7 groups = 224), one run per core per dispatch, cost](../novel-results/2026-10-18-preshader/README.md); open: coverage case, field 0 | safe-09 | Hoisting kernel-uniform values (`blockDim` products, argument pointers) | Execution model known |
| 6 | fmadd lane-offset: ~~write-to-read distance, inactive source lanes, simulator model~~ done ([2026-10-18](../novel-results/2026-10-18-fmadd-followups/README.md)); bit-52 rule resolved ([pow fixup](../novel-results/2026-10-18-fma-b52/README.md)); coverage cases for lane form and bit 52 recorded | safe-07 | A lane-shifted fma can replace `shfl.up` + `fma` in scans and stencils | Encodings found on 2026-10-11 |
| 7 | Cost-model gaps: per-line serialisation of colliding atomic lanes, strided access, barrier after ALU, store write-back, PTX-compliant sin/cos cost | safe-02 steps 1 (rest) - 5 | Performance stage (stage 4) and kernel-time prediction | Step 1 done |
| 8 | ~~SLC capacity by bandwidth~~ done 2026-10-18: [about 21 MiB effective, smooth 14-30 MiB, CPU-independent](../novel-results/2026-10-18-slc/README.md) | safe-03 (open part) | Cache-aware lowering and blocking | Latency could not separate the SLC |
| 9 | Textures and images through Mesa-compiled GLSL: encodings, filtering precision, unorm/snorm/sRGB rounding, borders, out-of-range coordinates, simulator model | safe-05 | `tex*`, `tld4`, `surf*` | Not started. Never hand-encode texture state |
| 10 | ~~Imageblock layouts and threadgroup-memory capacity~~ done 2026-10-18: [no effect on occupancy](../novel-results/2026-10-18-imageblock-occupancy/README.md) | safe-11 §2 | Whether tile memory shares the 64 KiB per core | SR12/13/15 identified |

### Gaps not yet covered by any task (safe to start)

- **fp64** (done 2026-10-18: [bit-exact software add / mul / fma, with costs](../novel-results/2026-10-18-fp64/README.md); open: div, sqrt, cvt, compares, other rounding modes). Original gap: AGX has no fp64 unit, and no finding documents that or measures it. CUDA `double` needs software
  emulation from recorded int64 and fp32 forms. Measure the cost of a double-precision add/mul/fma sequence built only
  from safe forms, and check it bit-exact against IEEE on edge cases.
- **64-bit atomics** (done 2026-10-18: [Honeykrisp exposes none; emulated add measured, final exact, returned value torn across the carry](../novel-results/2026-10-18-atom64/README.md); open: lock-based CAS / exchange, which needs a spin loop and the owner's approval) (`atom.add.u64`, `atom.cas.b64`, `atom.exch.b64`). No validated encoding is known. Device and
  threadgroup ops 11-15 stop the issuing group in the tested forms. Compile a Vulkan shader with
  `GL_EXT_shader_atomic_int64` (if exposed), export the binary and decode Mesa's lowering.
- **Warp shuffle completeness** (done 2026-10-18: [exact lowerings, quad-granular index](../novel-results/2026-10-18-shfl/README.md); open: partial membermask, 64-bit values, cost). Original task: Check that every `shfl.sync` mode (`up`, `down`, `bfly`, `idx`) with `c`-clamp and
  segment-mask operands has a recorded AGX lowering with exact out-of-range behaviour. The cross-lane width finding
  covers reductions and scans, not every shuffle form.
- **Stack / scratch through Mesa only** (done 2026-10-18: [spills, vec4, 16-bit; simulator replay exact](../novel-results/2026-10-18-stack-mesa/README.md); open: `stack_get_ptr`, async forms, the coverage case, spill cost). Original task: Capture a Mesa shader that spills (`stack-via-mesa`) and record the
  `stack_*` encodings as coverage cases, without hand-built helper programs (`MANUAL` item `stack`). CUDA local arrays
  and register spills depend on it.

### Coverage-suite housekeeping (offline or safe)

- (Done 2026-10-18: fmadd lane-offset cases recorded in the catalog; the other items are covered by `coverage.py properties` in AGX-Performance-Simulator, 17 verifiers.) Original item: add the remaining `MANUAL` items as catalog cases: `fmadd_lane_offset`, `stack`, `preshader`, `imageblock_srs`,
  `memory_ordering`, `occupancy`, `in_shader_clock` (each comes from its task above).
- Write `results/<date>-coverage/README.md`: pass counts per area, simulator mismatches by cause, faults,
  timing rows more than 10% off, nondeterministic cases (`tasks/agx-coverage.md` step 5).
- Report the `bfeil` verdict A upstream: Mesa's `fuse_ubfe` is unsound for variable shifts (m2-run-checklist Q1,
  with `viterbifix` as the workaround). This is outward-facing, so it needs the owner's go-ahead.

## Unsafe work (owner approval required)

Each item below either hung the GPU, wedged the device, or has no evidence that it is safe. Run them one at a time
after a reboot, check `gpu_safety.py status` between runs, and stop at the first fault. The device previously wedged
after about 44 recoveries in one boot.

### Needed for CUDA (worth the risk, with care)

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

1. safe-10 (memory ordering), because a wrong fence mapping produces silent wrong results.
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

- Textures (safe-05), partial 2026-10-18: [conversion, filtering and wrap rules measured](../novel-results/2026-10-18-gles-texture/README.md); still open: borders, 1D/3D/array targets, LOD/gradient, 16-bit and integer formats, simulator model, CUDA mapping table.
