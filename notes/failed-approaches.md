# Failed approaches and known limitations

| Date | Approach or check | Actual observation | Next action |
| --- | --- | --- | --- |
| 2026-10-04 | Discover libdrm through `pkg-config --modversion libdrm` | Package metadata was unavailable | Initial smoke test uses installed DRM headers and direct ioctl calls |
| 2026-10-04 | Reuse supplied applegpu hardware harness on Linux | Inspection found `xcrun` and Metal framework dependencies; execution was not attempted | Build a separate Linux/DRM execution backend; reuse offline tools as appropriate |
| 2026-10-04 | Identify board through `/proc/device-tree/model` and `compatible` | Both paths absent in the container | [Parameters now report G14C](../experiments/baseline/device-params.md); exact board and memory capacity remain unmeasured |
| 2026-10-04 | Discover Vulkan/OpenCL tooling on `PATH` | `vulkaninfo`, `clinfo`, `glslangValidator`, and `spirv-as` were not found | Inventory libraries before choosing a compute backend; tool absence alone does not prove API absence |

The DRM version smoke test has passed. No failed GPU shader submissions or
instruction probes have been observed yet. Add such failures with their inputs,
return codes, logs, and control result when they occur.

## Reviewed read-only probe failures

[Params evidence](../results/2026-10-04-device-params/README.md) retains missing
node (`ENOENT`), `/dev/null` version rejection (`ENOTTY`), wrong driver `apple`,
missing compiler, and invalid usage. The integration rerun repeated a missing
node failure. No unsupported GET_PARAMS or malformed kernel response was induced.

[Time evidence](../results/2026-10-04-driver-time/README.md) retains a missing
node and invalid argument bounds. Integration repeated `/dev/null` rejection
before GET_TIME. No unsupported GET_TIME, reset, or GPU submission was attempted.

Review found that the original time runner could accept zero or too few samples
and could crash on malformed JSON without a summary. The corrected runner
requires exact successful counts and validates metadata/sample fields before
analysis. [Synthetic regression evidence](../results/2026-10-04-driver-time/integration-review/verification.json)
shows malformed/empty/truncated data, failed records, invalid types, duplicate
indices, nonzero flags, invalid host brackets, backward time, and stalled time
all produce status 1 with `passed: false`. These are software failure injections,
not observed hardware faults. Available timeout output is retained; timeout and
permission failure paths were not induced in this review.

During final integration, another owner added a GLES C probe. The expanded default
`make check` failed on missing system `EGL/egl.h`. Supplying the unchanged Mesa
header include root via `CC='cc -I/save/workspace/AGX_Probe/mesa/include'` let all
four current C files pass syntax checking. That probe was outside the first integration commit. The subsequent P2 review
adds `PROBE_INCLUDE` to shared tooling so normal `make check` can use vendor
EGL/GLES/Vulkan headers without embedding include flags in `CC`.

## P2 and backend review

[P2](../experiments/baseline/compute-readback.md) now demonstrates actual GLES
compute/readback. Its stored wrong-oracle, invalid-GLSL, wrong-device, missing-
header/device, and host-only timeout/launch failures are selected evidence.
The original runner hardcoded `cc`; integration now honors `CC`. A missing
compiler override failed before API children, with a retained summary.

[Backend inventory](../results/2026-10-04-backend-inventory/README.md) records
historical Vulkan ICD loading failure due to `libdisplay-info.so.2`; this review
does not rerun or integrate the ongoing Vulkan owner's runtime work.
[Counter research](../results/2026-10-04-shader-counter-research/README.md)
found no justified shader timer selector. Inspected source writes both compute
timestamp destinations to `comp_start` and returns constant-zero disjoint state.
These predict timing hazards if present in the installed build; this review
measured neither broken command timestamps nor instruction latency.

## Multiply-add probe and delegation limitations

The pinned [imadd addend test](../experiments/arithmetic/imadd-addend.md) passed;
there was no observed GPU/import/oracle failure for the refreshed native patch.
The intentionally stale digest was rejected before dispatch. This supports the
pinned wrapper integrity behavior only. General addend carry, register coverage
and instruction timing remain untested.

This session's acm-dev native Claude/Grok CLI launches failed, and native Gemini
workers required authentication. OpenCode-backed Kimi K3 and GLM 5.3 performed
implementation/hardware and offline review respectively, but stopped during final
packaging on provider access/funding errors. Their code and passing raw evidence
were recovered; coordinator integration completed the reproducible artifacts.
Do not interpret a running process or provider failure as a completed review.

### Special-register scan, 2026-10-04

The full 0..255 sweep and separated paired reads found no progressing shader
clock through the tested 32-bit `get_sr` path. SR32 changes between fresh command
buffers, with the same 0x24000 step at counts 1, 33, 65, and 257; this is not a
workgroup-count or elapsed-time oracle. Its underlying cause remains unidentified.
Two local patch validations failed before a mutated shader submission: the main
metadata includes 16 padding bytes (70 total, rather than 54 executable bytes),
and a textual conditional-disassembly comparison was too brittle. Both failures
are retained with the successful original controls. Known `wait 0` padding was
used because the reference decoder supplied no established nop encoding.
Paid ACM workers failed on provider funding; explicit Copilot model names were
unavailable. The configured default Copilot worker completed three review turns
and contributed the independent verifier. See the
[hardware report](../experiments/registers/special-register-scan.md).

### SR geometry / bit-15 follow-up, 2026-10-10

* `/scratch/apple-m2-playground` was root-owned and not writable by the probe
  user (uid 1000) this session. Default runner outputs failed with `PermissionError`
  before any GPU work. Pass `--output` / `SCRATCH_ROOT=` to a writable directory.
  `make check` also needs `SCRATCH_ROOT` overridden in that case.
* The bit-15 `get_sr` form (applegpu `TODO.sr_thing`) is **not** an alternate
  read or a move-to-SR in compute. Without a preload it stores stale
  register-file contents, which can look like random data. Always preload the
  destination when testing a possibly non-writing instruction.
* SR15/19/24/25/97/114 do not depend on workgroup shape or count. Small
  shapes produce coincidental matches (e.g. `gx = 2` for SR24), so fit formulas
  across several shapes before naming a register.
* No GLSL/SPIR-V compiler is installed (no glslang/glslc/spirv-as). SPIR-V is
  hand-encoded from the Mesa grammar and validated with libSPIRV-Tools.
* A shader that routes data through threadgroup memory reads back 0 when its
  shared allocation is edited to 0. Threadgroup stores/loads then silently do
  nothing, with no fault. This was briefly mis-read as "SR19 = 0".
* Editing exported `main_offset` (0x849) makes the shader write nothing. It is not
  a tunable field.
* 64-bit / 16-bit `get_sr` destinations expose no hidden clock half. `get_sr` is
  32-bit only, and SR113 is intermittent (0/8) and must not be attributed to an edit.

### Undecoded-opcode execution, 2026-10-10 — SYSTEM-VISIBLE GPU FAULTS

`scripts/run_agx_opcode_scan.py` executes the 59 low-7-bit opcode values the
applegpu model cannot decode. Nine of them (0x06, 0x24, 0x34, 0x44, 0x46, 0x54,
0x5c, 0x64, 0x74), executed by even one lane, discard every store of the whole
dispatch. The submitting process sees **no error**: the fence signals and a second
submission on the same VkDevice succeeds. **The project owner saw purple flashes
and desktop stutter while these ran.** These are almost certainly whole-GPU fault
recovery events that the shared display also experiences. Do not interpret "no
VkResult error" as "no fault".

* Run these only with the owner's agreement, on an idle machine. Keep counts
  minimal and capture `dmesg` (needs root) around runs. `make opcode-scan` is
  gated by `CONFIRM_GPU_FAULTS=1`.
* Repeated firmware faults on Asahi can require a reboot. Note that risk before any rerun.
* Results so far are in scratch only and are not yet a retained finding. Class A
  (17 opcodes) end the executing SIMD group, and also act when the group has no
  active lanes unless jumped over. 0x18-like opcodes are no-ops. Some 0x6e operand
  forms return stale, bit-noisy on-chip data. That resembles the LeftoverLocals
  class (CVE-2023-4969) and was deliberately not pursued.

### Command timestamps and direct DRM, 2026-10-10

* **`Write; Dispatch; Write` timestamps measure nothing on Honeykrisp.** Both land
  on stream ends, and the first one marks the end of the dispatch. This was first
  read as "compute timestamps are broken". Record top-of-pipe plus a second stamp
  before the dispatch, or use direct DRM's start/end pair.
* **Clock state looked like code-size dependence.** iadd chains at 65536 seemed
  cheaper per instruction than at 32768. That was a mid-run clock-state switch, not
  layout. Always print per-sample times. A 1.5–1.7× jump between consecutive
  identical dispatches is a state change.
* **Unrolled code cannot measure ALU latency.** Dependent and independent chains
  cost the same because instruction fetch dominates (~1.84 ns/byte). Use small
  loops.
* **A quick oracle with hard-coded word offsets mis-reported a failure** (tail at
  word 72 instead of 80). Compute the whole expected buffer from count and layout,
  as `run_drm_compute.py` does.
* **Host time is not a timing source.** Identical empty DRM dispatches took 115 or
  577 µs host-side. Firmware timestamps stayed at 5.7–7 µs.
* The opcode-scan kernel log was captured after the fact, and that session's scan
  outputs were lost. Its 286 timeouts / 73 Unmapped read faults cannot be matched
  to opcodes. See [kernel log evidence](../results/2026-10-10-opcode-scan-kernel-log/README.md).

### Loops, 2026-10-10

* **Short loop bodies give impossible throughputs.** Four fadd32 chains × 64 steps
  measured 0.31 ns/instr (~3 instructions per cycle per SIMD group). Part of the
  ~86 ns per-iteration overhead overlaps with the body, so subtracting it as a
  constant fails. With 512-step bodies, 4 chains equal 2 chains. A 1-instruction
  body hides entirely.
* **"Two clock states" was an incomplete reading.** Runs of a few ms saw two levels;
  40-submit runs show ≥4 levels spanning 3.16×. Identify the state per sample.
* **Without `push_exec` before the loop,** finished lanes and out-of-bounds lanes
  share r0l = 1 after `while_icmp`, and the post-loop store would be skipped.
  Caught in design, not on hardware.
* applegpu's assembler needs `if_fcmp r0l, eq, 0.0, 0.0, 1` for `push_exec` and
  `pc+N` / `pc-N` branch syntax. A zero offset prints as `pc+0`.

### Pointer chase, 2026-10-10

* applegpu's `device_load` exec with a uniform base calls `Uniforms.get_reg64`
  with an extra thread argument and crashes. `agx_loop.emulate` subclasses
  `Uniforms` to accept it.
* Building a 256 MiB table as a Python list needs several GB. `chase_table` uses
  `array('I')` (1.3 s for 64 M words).
* The first coarse curve looked noisy at 16–64 KiB because of clock-state
  transitions inside short runs. Use ≥ 30 submits and report warm/cold windows
  separately.
* Elements exactly 16 KiB apart conflict in the first level: 64 such lines
  (4 KiB) miss although 8 KiB of contiguous lines hit. Do not use page-aligned
  strides to measure capacity.

### Direct-DRM SR scan, 2026-10-11

* applegpu cannot assemble `device_store ..., unsigned, 0` (the trailing `0` is the
  `u6` field, not a shift). `agx_loop.store` edits the control store's R/A/O fields
  and requires an exact decode round trip instead.
* "SR17 = SR53" held in every light-load shape and was nearly recorded as a
  duplicate. Only a high-occupancy dispatch separated them. Test candidate
  per-group registers under load as well as in isolation.
* Counting distinct SR17 values per core is not peak occupancy: sequential
  workgroups reuse different slots (1,024-thread groups at 256 registers used 36 IDs).
* Putting the preshader word anywhere but last makes the dispatch silently execute
  nothing. Check the output oracle and execution time; the submit does not fail.
* The first full-sweep run stored ~1.2 GB of raw JSON. Keep raw records in
  scratch and commit `extract_sr_scan.py` summaries.

### Preshader scan, 2026-10-11

* A runner bug passed the pairing slots (250..253) to the preamble as selectors, so
  the "main-shader" values read 0 everywhere, including SR24, which must be 2. A
  constant-writing preamble exposed it: the pairing slots held preamble constants.
  That session is omitted from retained evidence. Run a constant delivery control
  for every new data path.
* A non-atomic per-core counter (load/add/store) read 1, but overlapping runs could
  have produced the same result. The device atomic add was validated (65,536
  exact) and the count repeated with it.

### Custom helper program, 2026-10-11 — PROBABLE GPU HANG/RECOVERY

* Owner-approved. One submission of a hand-built helper (`run_drm_helper.py`): a
  256-selector scan stored through SR146/147, then a doorbell loop. The submit
  "succeeded", but it took 0.50 s, firmware timestamps were not written, and each
  helper stopped after 7 of 256 stores. Treat it as a hang recovered by firmware.
  See [evidence](../results/2026-10-11-helper-attempt/README.md).
* Do not judge success from syncobj wait alone. Check host time and whether the
  firmware timestamps were written (0/0 means the command did not complete
  normally).
* Retried Mesa-shaped (doorbell first, r0–r6): the same 0.5 s hang, and the
  helper never returned from its first doorbell. Helper probing is dropped. A
  future attempt would first need the conditions under which firmware feeds
  helper requests/END (cfg, binary tag bits, stack-using main, scratch header),
  e.g. from a trace of Mesa running a spilling shader.

### Direct-DRM opcode scan, 2026-10-11 — DEVICE WEDGE ON 0x5c

* 0x5c on the direct DRM path did not recover the way the other faulting opcodes did.
  Its own dispatch hit the 3 s syncobj ceiling, and every later SUBMIT failed with
  ETIME until the machine was **rebooted**. In the Vulkan scan, the same opcode
  appeared to recover. A clean recovery in one path does not predict the other.
* After the reboot, the owner allowed only opcodes that had never crashed. The 16
  remaining ones ran with `--max-faults 1` and produced 0 faults. 0x5c, 0x64 and 0x74 stay
  unrun. See [evidence](../results/2026-10-11-opcode-scan-drm/README.md).

### Opcode descriptions, 2026-10-11

* **Register count is in 16-bit halves.** `--gprs 32` declares r0–r15 only. A probe that used
  r0–r26 under it passed 890 of 894 dispatches. The other 4 (the slowest, > 15 µs) lost or
  misplaced stores. None reproduced on rerun, and one of them never executed the opcode
  under test. Before blaming an opcode, check the declared count against the highest
  register used (×2).
* **Do not subtract an empty loop to get per-instruction ns.** Short bodies overlap the
  taken-branch overhead, so the costs do not add. Absolute loop times also varied 2.2×
  between processes (the 462 / 336 / 213 µs states). Compare raw times from the same run.
  A repeat that gave `mov_imm` at 0.31 ns instead of 2.26 ns exposed this.
* A "no-op" verdict from a scan with `wait` padding hides the instruction length. Every
  low-`0b11` opcode is 6 bytes and swallowed the padding. Use the marker layout
  (`mov_imm rNl, 56` = `62 xx 38 00`, upper half `wait`) whenever length matters.
* The brief given to delegated agents listed 0x6f as a scanned no-op, and both agents
  repeated it. 0x6f is decoded by applegpu (subgroup op), and the 33 no-ops include 0x78. Derive
  opcode lists from the retained scan record, not from summaries.
* Delegation 2026-10-11: AGY (Antigravity) needs an interactive Google login (`agy`), and
  its run failed at authentication. OpenCode's run ended with ECONNRESET after it had
  written its report. Only Claude submitted GPU work; the delegated agents were offline-only.

### Sync probes, 2026-10-11

* **Short timing dispatches are unusable for small differences.** A < 1 ms loop flipped from
  831 to 382 µs mid-session on the same core (SR20). Bracketing each candidate with references
  kept too few stable pairs and once gave a negative cost. 50,000-trip dispatches (about 6.5 ms)
  have a floor stable to < 1.5%; take the minimum.
* Multi-SIMD-group timing on one core is confounded by issue contention: `wait` alone measured
  1.5 ns in one run and 13 ns in another at 8 groups. Do not infer a shared unit from that.
* Not run on purpose: a group ending (stop/ends) while another waits at a barrier, and
  0x68/0x78 executed by different groups at the same point. Either could deadlock the
  workgroup, i.e. cause a GPU timeout/fault.
* applegpu's assembler cannot encode `threadgroup_load/store` (no `encode_string` for the base).
  Pack them from Mesa `agx_pack.c:769-792` and require an exact decode.

### Barrier stress, 2026-10-11

* **A light barrier test can hide a scoped barrier.** The delayed-flag test with 2 and 4 SIMD groups
  passed 0x78, which was then called a whole-workgroup barrier. Only 8+ groups showed that it covers
  aligned blocks of 4. Test barriers at the largest workgroup sizes, with partners in distant groups.
* **(Resolved: index operand stride, see below.)** Only declared/4 bytes seemed usable. Declaring 8 KiB
  for 8 KiB of data made 0x68 and 0x78 fail identically, which first looked like a barrier result.
  Identical failure counts across different barriers point to the harness.
* With large threadgroup allocations (one workgroup per core), 2-group workgroups ran in lockstep and
  the `wait` negative control stopped failing. Always keep a control that is shown to fail.

### Threadgroup addressing, 2026-10-11

* The "declared/4" capacity was not a size-field bug. The `threadgroup_*` **index** operand counts
  4-component slots (16 bytes for i32). Use Mesa's form instead: byte offset in the base register,
  index 0. Before concluding that a size field has the wrong units, check how the probe addresses memory.

### In-shader clock, 2026-10-11

* Polling a CPU-written word from a shader returned the same value for the whole dispatch,
  even with Mesa's coherent load bit. The GPU caches the line after the first read. Re-read
  with `device_barrier_1`/`unknown_barrier_1` + a coherent load, or read a line not yet touched.


### Grid-size caps, 2026-10-11

* **A previous session raised the 65536-thread harness cap straight to 2^20 and the host crashed
  (kernel/machine down, reboot needed).** That edit was never committed, and no kernel log from that
  boot survived, so the exact launch is unknown. The control main only stores `out[8 + x]` when
  `x < count`, and the CDM global-size fields are 32-bit, so neither explains it by itself.
  Retry plan (this session): caps raised to 2^24 with the table moved past a large output; step one
  power of two at a time, separately for a large X grid (output scales) and a large Y grid (output
  fixed at 32 lanes), one process per step, pushing before each new size.
* **Outcome:** the retry passed every step from 2^16 to 2^24 threads, X and Y forms, with exact
  buffers ([runs](../results/2026-10-11-grid-size-cap/README.md)). The crash was in that session's
  uncommitted harness edit (most likely the output/table/BO sizing), not in the grid size. When raising a
  bound, keep every derived size (output words, BO size, table offset) consistent and step up gradually.
* **`count` sets global X in `tests/drm_compute.c`.** The first coverage kernel passed `count` (= output
  lanes) and got a count×gy grid instead of 32×gy. Threads then wrote other rows' slots with their own y,
  which looked like `sr81` saturating at 1, and a 2^16 run stored past the end of the output with no bounds
  check (no fault or kernel message seen). Use `AGX_GLOBAL_X` to decouple the grid from the output size,
  and keep an `index < count` check in any probe that computes store indices from SRs.

### ISA bit mapping session, 2026-10-11 (device wedged at the end)

* **Recovered GPU timeouts accumulate; after ~44 in one boot the device wedged.** Every hang in this
  session (24 funop functions, 2 convert round values, 5 constant-bit flips, 4 fixed TODO
  encodings) was followed by a passing control dispatch. The last one, `TODO.unk0C00` (0x000c),
  logged an unmapped UL1C read at 0x1000000900 during recovery; one control still passed, then
  every later submit failed with syncobj ETIME (3 s, no firmware timestamps) and "Job canceled on
  DRM scheduler teardown". Same signature as the 0x5c wedge: reboot required.
  Run known-hanging encodings at most once, and run them last. Prefer sweeps that are proven
  hang-free (`--max-faults` small) and reboot between batches that are expected to hang.
* Not run because of the wedge: the device `atomic` sweep (op 0–15, bits 25, 26, 28–31, 42–46 of
  the `1500208e10500400` form with a return value in r5). The runner call is in the session's
  `scripts/run_drm_bitflip.py --raw` usage; nothing about atomics was measured.
* `kernel.log` in the workspace is live (it shows these timeouts); earlier notes calling it a boot snapshot were wrong.

### Instruction benchmark timing, 2026-10-11

* **Whole-dispatch firmware times across separate dispatches cannot give cycles.** The GPU clock
  moves between at least 419, 922, 1,058, 1,330 and 1,398 MHz between and within dispatches; a
  two-dispatch slope gave negative and inconsistent throughputs (even `fadd32 x, x, 0.125`).
  Calibrate inside the dispatch with the CPU timer and a reference chain instead (`run_bench.py`).
* **Per-group slopes are wrong in GPU-wide runs.** SIMD groups start up to 1.7 ms apart and
  groups sharing a busy unit (rcp, rsqrt) are not scheduled fairly, so a group's phase overlaps
  other groups' different phases. Aggregate per core (SR20) using first-in/last-out phase spans.
* **8 SIMD groups per core breaks the in-dispatch reference.** The dependent iadd reference then
  needs the core's whole issue rate; inferred clocks ranged 244–2,547 MHz. Throughput above
  4 groups per core is therefore unmeasured.

### Cost model, 2026-10-11

* **"Loop bodies over ~512 B / 64 instructions fetch slowly" was wrong.** A body of 9 instructions repeated
  8 times ran 2× slower, but bodies of up to 2 KiB of independent 8-byte iadds run at one per cycle
  (`fetch-body-size.json`). The trigger was 9+ distinct destination registers (the result-cache finding).
* **Whole-dispatch firmware time across dispatches** cannot calibrate cycles (see the instruction benchmark
  notes above); the cost model is validated only with the in-dispatch CPU timer.
* **Issue-interval rules.** Letting a multi-cycle instruction block only its own unit family matches
  "leader + k independent iadds" tests (3.9%) but triples the random-kernel error (4.3% → 14.8%); one shared
  pipe for all multi-cycle classes is in between. The default blocks the whole group. The true rule is open.
* **Shared execution-unit buckets did not explain the 4-group slowdown.** Measured 4-group / 1-group body
  time is 1.07 (median, 0.97–1.34) over 60 kernels and correlates with the transcendental share (+0.44) and
  inversely with SIMD reductions (−0.49). Making transcendentals (and imad/bitfield/convert) draw on one
  shared bucket per unit, weighted by each op's measured rate, left every prediction unchanged: the
  model's units never saturate in these latency-bound kernels. Reverted; the cause is open.

### Core scaling beyond 4 SIMD groups, 2026-10-11

* **Short loop bodies give impossible core throughput with many groups.** 8/32-step bodies gave 5.3
  instructions per cycle at 16 groups and *less* at 8 than at 4. With 32/128 steps the core saturates at
  exactly 4.0. The same bias hides in the instruction bench's 4-group column (16/64 steps): shared-unit ops
  look up to 2× faster there than with 32/128 steps, in either timing method.
* **Selecting "group 0" with `r1 & (32*G - 1)` only works for power-of-two workgroups.** For G = 12, 15, 24
  several groups ran the reference and the inferred clock was wrong (one run gave 50 cycles per step).
  Use SR53 (SIMD-group index in the workgroup).
* **A probe's own bookkeeping can clobber its parameters**: the per-group OP trip count first lived in r29,
  which the SR17 recording also wrote, and every OP loop ran one trip (~0.04 cycles per step). Check that
  each phase register is written after every other setup block.
* **Removing the barriers** to test lockstep effects breaks the one-group reference (group 0's timestamps no
  longer bracket the others' work).
