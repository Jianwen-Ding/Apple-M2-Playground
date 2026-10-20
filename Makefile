PYTHON ?= python3
SCRATCH_ROOT ?= /scratch/apple-m2-playground
DEVICE ?= /dev/dri/renderD128
PROBE_INCLUDE ?= /save/workspace/AGX_Probe/mesa/include
APPLEGPU_ROOT ?= /save/workspace/AGX_Probe/applegpu
MESA_ROOT ?= /save/workspace/AGX_Probe/mesa
export CC PROBE_INCLUDE

.PHONY: help atomic-variants verify-atomic-variants atomic-contention verify-atomic-contention cpu-gpu-visibility verify-cpu-gpu-visibility verify-l2-command-boundary verify-memory-parameters cache-line verify-cache-line fixed18-waits verify-fixed18-waits queue-concurrency verify-queue-concurrency queue-priority verify-queue-priority commands-per-submit verify-commands-per-submit drm-limits drm-sync submit-latency verify-submit-latency verify-drm-interface verify-transcendentals sr113-timeline verify-special-registers sr-vm-slot sr-divergence sr113-reps verify-cross-lane-width verify-battery-clock-states env check smoke params time compute instruction-candidates agx-instruction agx-imadd verify-imadd sr-scan sr-pairs sr-characterize sr-even sr-context verify-sr sr-shape sr-core sr-alt sr-alt-reread sr-std-preload verify-sr-shape sr-shared sr-meta sr-width verify-sr-resources opcode-scan timestamps verify-timestamps drm-compute grid-cap grid-coverage verify-alu-bitflip verify-fmadd-decode verify-fmadd-lane verify-subop-spaces verify-mem-control-bitflip gpu-faults agx-loop-test verify-loops agx-loops agx-memory verify-memory agx-bandwidth sr-direct verify-sr-direct opcode-describe test-opcode-describe verify-opcode-describe sync-probe test-sync-and-end verify-sync-and-end barrier-stress test-barrier-stress verify-barrier-stress test-tg-addressing verify-tg-addressing test-in-shader-clock verify-in-shader-clock test-atomics verify-atomics test-float-semantics verify-float-semantics test-int64 verify-int64 test-occupancy verify-occupancy test-memory-ordering verify-memory-ordering test-sb-lb verify-sb-lb verify-sb-minimal test-fence-contention verify-fence-contention verify-fixup-cost verify-tg-end-scope verify-bfeil-verdict verify-atomic-pairs verify-fcmp-extra verify-fcmp16 verify-fcmp64 test-atomic-release verify-atomic-release test-dispatch-visibility verify-dispatch-visibility verify-fence-cost verify-fence-model verify-tg-litmus verify-fcmp verify-softfp64 verify-fp64-divsqrt verify-shfl verify-occupancy2 verify-clock2 verify-clock-model verify-atom64 verify-preshader verify-stack-mesa verify-fmadd-followups verify-fma-b52 verify-slc verify-imageblock-occ verify-gles-texture verify-texture-edge verify-texture-targets verify-texture-unit verify-spill-cost verify-sincos-cost verify-barrier-cost bench verify-bench verify-core-scaling verify-memory-hierarchy verify-dispatch verify-shared-memory-sync

help:
	@echo 'make env    Capture environment metadata without opening the GPU'
	@echo 'make check  Check Python and C syntax without opening the GPU'
	@echo 'make smoke  Compile and run the DRM access test'
	@echo 'make params Query Asahi identity/topology (3 repeats)'
	@echo 'make time   Query driver timestamps (264 samples; no shader)'
	@echo 'make compute Build and verify a bounded GLES compute smoke test'
	@echo 'make agx-instruction Run the pinned G14C move-immediate hardware suite'
	@echo 'make agx-imadd Run the pinned G14C multiply-add addend hardware suite'
	@echo 'make verify-imadd Verify retained multiply-add evidence offline'
	@echo 'make instruction-candidates Export offline AGX ALU bytes/oracles; no GPU access'
	@echo 'make sr-scan / sr-pairs Scan special registers on hardware'
	@echo 'make sr-characterize / sr-even Check lane-mask behavior'
	@echo 'make sr-context Check repeated dispatches in one device'
	@echo 'make verify-sr Verify retained special-register evidence offline'
	@echo 'make sr-shape / sr-core / sr-alt Workgroup-shape, core-id, bit-15 form probes'
	@echo 'make verify-sr-shape Verify retained shape/core/bit-15 evidence offline'
	@echo 'make sr-shared / sr-meta / sr-width SR18/SR19 resource and get_sr width probes'
	@echo 'make verify-sr-resources Verify retained resource/width evidence offline'
	@echo 'make timestamps         Hardware regression: Vulkan timestamp placement (~10 ms shader time)'
	@echo 'make verify-timestamps  Verify retained timestamp/fetch/direct-DRM evidence offline'
	@echo 'make grid-cap           Control dispatch at 2^16..2^24 threads, X and Y forms (direct DRM)'
	@echo 'make grid-coverage      Check every sampled row of 2^16..2^30-thread grids executes (direct DRM)'
	@echo 'make verify-alu-bitflip  Verify retained ALU bit-flip / fmadd lane-offset evidence offline'
	@echo 'make verify-fmadd-decode  Verify the simulator decodes retained fmadd programs (10-byte lane form) on exact boundaries'
	@echo 'make verify-fmadd-lane    Replay retained fmadd lane-offset programs in the Rust simulator (needs agx_run built)'
	@echo 'make verify-subop-spaces Verify funop/iunop/simd_op/shuffle sub-op sweeps offline'
	@echo 'make drm-limits    Host-side Asahi DRM interface limits (ioctls only, no GPU work submitted)'
	@echo 'make drm-sync      GPU: cross-queue ordering via binary / timeline syncobjs (agx_run-gated kernel)'
	@echo 'make submit-latency GPU: SUBMIT -> firmware start versus idle gap (agx_run-gated control kernel)'
	@echo 'make verify-submit-latency Verify the launch-latency / GPU wake-up evidence offline'
	@echo 'make commands-per-submit GPU: N commands per SUBMIT (chain / none) and the clock ramp (agx_run-gated)'
	@echo 'make verify-commands-per-submit Verify the commands-per-submit / clock-ramp evidence offline'
	@echo 'make queue-priority GPU: priority 1 vs 0 against a saturating low-priority process (agx_run-gated)'
	@echo 'make verify-queue-priority Verify the queue-priority evidence offline'
	@echo 'make queue-concurrency GPU: how many queues execute at once (agx_run-gated kernel)'
	@echo 'make verify-queue-concurrency Verify the 4-concurrent-commands evidence offline'
	@echo 'make fixed18-waits  GPU: what 0x18 waits for, with the clock keeper (agx_run-gated)'
	@echo 'make verify-fixed18-waits Verify the 0x18 wait evidence offline'
	@echo 'make cache-line     GPU: line size per level, neighbour test with the clock keeper (agx_run-gated)'
	@echo 'make verify-cache-line Verify the 64-byte line evidence offline'
	@echo 'make verify-l2-command-boundary Verify that other processes\' command boundaries evict L2 (offline)'
	@echo 'make verify-memory-parameters Verify TLB reach / L1 / L2 / SLC latency curves (offline)'
	@echo 'make cpu-gpu-visibility GPU: CPU<->GPU visibility ping-pong (fixed counts, agx_run-gated)'
	@echo 'make verify-cpu-gpu-visibility Verify the CPU<->GPU visibility evidence offline'
	@echo 'make atomic-variants    GPU: unnamed device-atomic encodings (fadd32, u64 min/max, ops 11-15; CONFIRM_GPU_FAULTS=1)'
	@echo 'make verify-atomic-variants Verify the atomic-variant evidence offline'
	@echo 'make atomic-contention GPU: same-address / spread device-atomic throughput (agx_run-gated, clock keeper)'
	@echo 'make verify-atomic-contention Verify the atomic contention evidence offline'
	@echo 'make verify-drm-interface Verify the recorded DRM interface limits offline'
	@echo 'make verify-battery-clock-states Verify the on-battery clock-state / llvmpipe-fallback evidence offline'
	@echo 'make verify-transcendentals Verify the exp2 / sin_pt_2 algorithms and PTX accuracy evidence offline'
	@echo 'make verify-special-registers Verify SR21 VM slot / SR113 / divergence evidence offline'
	@echo 'make sr-vm-slot      GPU: SR21 across 16 concurrent + 70 sequential VMs (direct DRM)'
	@echo 'make sr-divergence   GPU: all 256 SRs inside nested ifs (direct DRM)'
	@echo 'make sr113-timeline  GPU: SR113 before/after each submission: sustained load, then 0-4 ms idle gaps (direct DRM)'
	@echo 'make sr113-reps      GPU: SR113 per submission, one process at a time (direct DRM)'
	@echo 'make verify-cross-lane-width Verify 16/64-bit cross-lane ops and the Sklansky SIMD scan offline'
	@echo 'make verify-mem-control-bitflip Verify memory/control/SR gap-bit evidence offline'
	@echo 'make drm-compute        Direct DRM (no Mesa) control + fadd4/iadd8 chain dispatches'
	@echo 'make agx-loop-test      Loop emulator gate tests + 3 small hardware loops (direct DRM)'
	@echo 'make verify-loops       Verify retained loop latency/throughput evidence offline'
	@echo 'make agx-loops          Reproduce the loop latency/throughput matrix (~1 min GPU time)'
	@echo 'make agx-memory         Pointer-chase load latency, 2 KiB..256 MiB (~4 min GPU time)'
	@echo 'make agx-bandwidth      Load overlap (1..16 chains) and streaming read bandwidth (~3 min)'
	@echo 'make verify-memory      Verify retained load-latency evidence offline'
	@echo 'make sr-direct          Differential 256-selector SR scan over launch parameters (direct DRM, ~5 min)'
	@echo 'make verify-sr-direct   Verify retained direct-DRM SR scan summaries offline'
	@echo 'make gpu-faults LOG=... Summarize Asahi GPU timeouts/faults in a kernel log'
	@echo 'make opcode-scan        GPU-FAULTING: undecoded opcode effects (needs CONFIRM_GPU_FAULTS=1)'
	@echo 'make opcode-describe    Describe the 49 non-faulting undecoded opcodes (needs CONFIRM_GPU_FAULTS=1)'
	@echo 'make test-opcode-describe  Hardware regression subset for the opcode descriptions'
	@echo 'make verify-opcode-describe  Verify retained opcode-description evidence offline'
	@echo 'make sync-probe         0x18/0x78 barrier/wait tests and ending-opcode tests (needs CONFIRM_GPU_FAULTS=1)'
	@echo 'make test-sync-and-end  Hardware regression subset for the sync/end finding'
	@echo 'make verify-sync-and-end  Verify retained sync/end evidence offline'
	@echo 'make barrier-stress     0x68 vs 0x78 message-passing stress test (needs CONFIRM_GPU_FAULTS=1)'
	@echo 'make test-barrier-stress  Hardware regression subset for 0x68 vs 0x78'
	@echo 'make verify-barrier-stress  Verify retained barrier-stress evidence offline'
	@echo 'make test-tg-addressing  Hardware: rerun the threadgroup-memory addressing probe and check it'
	@echo 'make verify-tg-addressing  Verify retained threadgroup addressing evidence offline'
	@echo 'make test-in-shader-clock  Hardware: CPU-written timer read inside a shader'
	@echo 'make verify-in-shader-clock  Verify retained in-shader clock evidence offline'
	@echo 'make test-atomics       Hardware: device + threadgroup atomics, Mesa ops 0-10 only'
	@echo 'make verify-atomics     Verify retained atomics evidence offline'
	@echo 'make test-float-semantics  Hardware: fp32/fp16 add/mul/fma rounding, denormals, NaN, saturate'
	@echo 'make verify-float-semantics  Verify retained float evidence offline'
	@echo 'make test-int64         Hardware: 64-bit add/sub/imad forms and 64-bit pointer loads'
	@echo 'make verify-int64       Verify retained 64-bit evidence offline'
	@echo 'make test-occupancy     Hardware: resident SIMD groups per core vs declared registers'
	@echo 'make verify-occupancy   Verify retained occupancy evidence offline'
	@echo 'make test-memory-ordering  Hardware: cross-workgroup message-passing litmus'
	@echo 'make verify-memory-ordering  Verify retained memory-ordering evidence offline'
	@echo 'make test-dispatch-visibility / verify-dispatch-visibility  Hardware / offline: stores of one dispatch seen by the next'
	@echo 'make verify-barrier-cost  Offline: barrier cost after ALU work'
	@echo 'make verify-sincos-cost  Offline: PTX-compliant sin sequence cost'
	@echo 'make verify-spill-cost  Offline: register spill cost (rough)'
	@echo 'make verify-gles-texture  Offline: Mesa GLES texture and image conversion rules'
	@echo 'make verify-texture-targets  Offline: 3D/array/cube/buffer targets, filter weight and LOD precision'
	@echo 'make verify-imageblock-occ  Offline: imageblock layouts do not change threadgroup-memory occupancy'
	@echo 'make verify-slc  Offline: shared-cache capacity by bandwidth, CPU sharing, cost-model SLC capacity'
	@echo 'make verify-fma-b52  Offline: fmadd32 bit 52 = pow special-case fixup (hardware results, simulator, historical records)'
	@echo 'make verify-fmadd-followups  Offline: fmadd lane-offset distance sweep and masked source lanes'
	@echo 'make verify-stack-mesa  Offline: Mesa spill / private-array stack encodings and simulator replay'
	@echo 'make verify-preshader  Offline: uniform file size, preamble runs per dispatch, registers, cost'
	@echo 'make verify-atom64  Offline: emulated 64-bit atomic add (retained hardware runs + simulator replay)'
	@echo 'make verify-clock-model  Offline: the cost-model clock-read table equals the retained sweeps'
	@echo 'make verify-clock2  Offline: in-shader clock cost under load and per-core timer copies'
	@echo 'make verify-occupancy2  Offline: workgroup slots, 2-D/3-D shapes, registers x threadgroup memory'
	@echo 'make verify-shfl-mask  Offline: sparse-mask index initialization and paired 64-bit shuffle payloads'
	@echo 'make verify-shfl  Offline: exact PTX shfl.sync lowerings (retained hardware run + simulator replay)'
	@echo 'make verify-softfp64  Offline: bit-exact software fp64 add/mul/fma (simulator replay + retained hardware runs)'
	@echo 'make verify-fp64-divsqrt  Offline: bit-exact fp64 div/sqrt/rcp/cvt, all rounding modes (simulator replay + retained hardware runs)'
	@echo 'make verify-fcmp  Offline: fp32 compare semantics, exact setp/min/max fix-up, simulator replay'
	@echo 'make verify-tg-litmus  Offline: threadgroup-memory MP/SB/LB litmus (hardware: scripts/run_drm_litmus_tg.py)'
	@echo 'make verify-fence-model  Offline: the simulator cost model of memory_barrier against the measured fence costs'
	@echo 'make verify-fence-cost  Offline: barrier costs (hardware: scripts/probe_fence_cost.py hardware)'
	@echo 'make test-atomic-release / verify-atomic-release  Hardware / offline: atomic flag as release litmus'
	@echo 'make test-sb-lb / verify-sb-lb  Hardware / offline: store-buffering and load-buffering litmus'
	@echo 'make verify-sb-minimal  Verify the minimal SB fence-set evidence offline'
	@echo 'make test-fence-contention / verify-fence-contention  Hardware (smoke) / offline: multi-group fence cost'
	@echo 'make verify-fcmp-extra / verify-fcmp16  Offline: setp .u/float-extension and fp16-compare evidence'
	@echo 'make verify-fixup-cost  Offline: fix-up cycle-cost evidence'
	@echo 'make verify-memory-hierarchy  Verify retained memory-hierarchy evidence offline'
	@echo 'make verify-shared-memory-sync  Verify retained threadgroup-memory/barrier/atomic evidence offline'
	@echo 'make verify-dispatch    Verify retained launch-cost and placement evidence offline'
	@echo 'make verify-core-scaling  Verify retained core-scaling (1-32 SIMD groups per core) evidence offline'
	@echo 'make bench              Hardware: latency/issue/per-core throughput for 60 instruction forms (~30 min)'
	@echo 'make verify-bench        Verify retained benchmark evidence offline'
	@echo 'Candidate references: APPLEGPU_ROOT and MESA_ROOT.'
	@echo 'Override SCRATCH_ROOT, DEVICE, PYTHON, CC, or PROBE_INCLUDE as needed.'

env:
	$(PYTHON) -B scripts/run.py env --scratch-root "$(SCRATCH_ROOT)"

check:
	$(PYTHON) -B scripts/run.py check --scratch-root "$(SCRATCH_ROOT)"

smoke:
	$(PYTHON) -B scripts/run.py drm-smoke --scratch-root "$(SCRATCH_ROOT)" --device "$(DEVICE)"

params:
	$(PYTHON) -B scripts/run.py params --scratch-root "$(SCRATCH_ROOT)" --device "$(DEVICE)"

time:
	$(PYTHON) -B scripts/run.py time --scratch-root "$(SCRATCH_ROOT)" --device "$(DEVICE)"

compute:
	$(PYTHON) -B scripts/run.py compute --smoke --scratch-root "$(SCRATCH_ROOT)" --device "$(DEVICE)"

instruction-candidates:
	$(PYTHON) -B scripts/agx_instruction_candidates.py --applegpu-root "$(APPLEGPU_ROOT)" --mesa-root "$(MESA_ROOT)" --output "$(SCRATCH_ROOT)/agx-instruction-candidates.json"

agx-instruction:
	$(PYTHON) -B scripts/run_vulkan_compute.py --probe-mov --include "$(PROBE_INCLUDE)" --grammar "$(MESA_ROOT)/src/compiler/spirv/spirv.core.grammar.json" --runtime "$(SCRATCH_ROOT)/vulkan-runtime/usr/lib64"

agx-imadd:
	$(PYTHON) -B scripts/run_agx_imadd.py --include "$(PROBE_INCLUDE)" --grammar "$(MESA_ROOT)/src/compiler/spirv/spirv.core.grammar.json" --runtime "$(SCRATCH_ROOT)/vulkan-runtime/usr/lib64"

verify-imadd:
	$(PYTHON) -B tests/test_agx_imadd.py
	$(PYTHON) -B scripts/verify_imadd_evidence.py novel-results/2026-10-04-imadd-addend --self-test --baseline-run "$(SCRATCH_ROOT)/absent-baseline"

sr-scan:
	$(PYTHON) -B scripts/run_agx_sr_scan.py --selectors all --repeats 3

sr-pairs:
	$(PYTHON) -B scripts/run_agx_sr_scan.py --selectors all --repeats 3 --count 16 --pair-gap 128

sr-characterize:
	$(PYTHON) -B scripts/characterize_agx_sr.py

sr-even:
	$(PYTHON) -B scripts/run_agx_sr_scan.py --selectors 80,0,48,16,56,57,58,59,60,63 --even-mask --count 33 --repeats 3

sr-context:
	$(PYTHON) -B scripts/run_agx_sr_context.py

verify-sr:
	$(PYTHON) -B scripts/verify_sr_findings.py
	$(PYTHON) -B scripts/verify_sr_evidence.py --selftest results/2026-10-04-sr-scan/full-single.json
	$(PYTHON) -B scripts/verify_sr_evidence.py --selftest results/2026-10-04-sr-scan/full-paired.json

sr-shape:
	$(PYTHON) -B scripts/run_agx_sr_shape.py --output "$(SCRATCH_ROOT)/sr-shape-runs/$$(date -u +%Y%m%dT%H%M%SZ)"

sr-core:
	$(PYTHON) -B scripts/run_agx_sr_scan.py --selectors 80,0,20,21,7,15,19,24,25,32,97,113,114,8,9,10,60,63,1,2 --repeats 3 --count 65536 --output "$(SCRATCH_ROOT)/sr-scan-runs/core-$$(date -u +%Y%m%dT%H%M%SZ)"

sr-alt:
	$(PYTHON) -B scripts/run_agx_sr_scan.py --alt --preload 0xdeadbeef --selectors all --repeats 2 --count 65 --output "$(SCRATCH_ROOT)/sr-scan-runs/alt-$$(date -u +%Y%m%dT%H%M%SZ)"

sr-alt-reread:
	$(PYTHON) -B scripts/run_agx_sr_scan.py --alt --reread --preload 0x5a5a1234 --selectors all --repeats 2 --count 65 --output "$(SCRATCH_ROOT)/sr-scan-runs/alt-reread-$$(date -u +%Y%m%dT%H%M%SZ)"

sr-std-preload:
	$(PYTHON) -B scripts/run_agx_sr_scan.py --preload 0x5a5a1234 --selectors all --repeats 2 --count 65 --output "$(SCRATCH_ROOT)/sr-scan-runs/std-preload-$$(date -u +%Y%m%dT%H%M%SZ)"

verify-sr-shape:
	$(PYTHON) -B scripts/verify_sr_shape_core.py --selftest

sr-shared:
	$(PYTHON) -B scripts/run_agx_sr_shape.py --shapes 0 --shared-words 0,32,64,128,256,512,1024,2048,4096,8192 --selectors all --output "$(SCRATCH_ROOT)/sr-shape-runs/shared-$$(date -u +%Y%m%dT%H%M%SZ)"
	$(PYTHON) -B scripts/run_agx_sr_shape.py --shapes 0 --shared-words 33,63,65,100,129,1000,4097,8000 --selectors 18,19,80 --output "$(SCRATCH_ROOT)/sr-shape-runs/shared-gran-$$(date -u +%Y%m%dT%H%M%SZ)"

sr-meta:
	$(PYTHON) -B scripts/run_agx_sr_meta.py --output "$(SCRATCH_ROOT)/sr-meta-runs/$$(date -u +%Y%m%dT%H%M%SZ)"

sr-width:
	$(PYTHON) -B scripts/run_agx_sr_scan.py --preload 0x5a5a1234 --width 64 --selectors all --repeats 2 --count 65 --output "$(SCRATCH_ROOT)/sr-scan-runs/w64-$$(date -u +%Y%m%dT%H%M%SZ)"
	$(PYTHON) -B scripts/run_agx_sr_scan.py --preload 0x5a5a1234 --width 16 --selectors all --repeats 2 --count 65 --output "$(SCRATCH_ROOT)/sr-scan-runs/w16-$$(date -u +%Y%m%dT%H%M%SZ)"

verify-sr-resources:
	$(PYTHON) -B scripts/verify_sr_resources.py --selftest

OPSCAN = $(PYTHON) -B scripts/run_agx_opcode_scan.py
OPDIR = $(SCRATCH_ROOT)/opcode-scan-runs/$$(date -u +%Y%m%dT%H%M%SZ)
opcode-scan:
	@test "$(CONFIRM_GPU_FAULTS)" = 1 || { echo 'opcode-scan executes instructions that fault the whole GPU (display stalls/purple flashes on the desktop). Re-run with CONFIRM_GPU_FAULTS=1 only on an otherwise idle machine.'; exit 1; }
	$(OPSCAN) --follow --output "$(OPDIR)-plain"
	$(OPSCAN) --bracket --output "$(OPDIR)-bracket"
	$(OPSCAN) --bracket --after-stop --output "$(OPDIR)-after-stop"
	$(OPSCAN) --set wg0-skip --count 257 --repeats 3 --follow --output "$(OPDIR)-wg0-skip"
	$(OPSCAN) --set 6e-fuzz --output "$(OPDIR)-6e-fuzz"
	$(OPSCAN) --set 6e-init --repeats 3 --output "$(OPDIR)-6e-init"


timestamps:
	$(PYTHON) -B tests/test_command_timestamps.py --runtime "$(SCRATCH_ROOT)/vulkan-runtime/usr/lib64" --output "$(SCRATCH_ROOT)/timestamp-runs/test-$$(date -u +%Y%m%dT%H%M%SZ)"

verify-timestamps:
	$(PYTHON) -B scripts/verify_command_timestamps.py

DRMDIR = $(SCRATCH_ROOT)/drm-compute/runs/$$(date -u +%Y%m%dT%H%M%SZ)
drm-compute:
	$(PYTHON) -B scripts/run_drm_compute.py --kind control --count 257 --device "$(DEVICE)" --output "$(DRMDIR)-control"
	$(PYTHON) -B scripts/run_drm_compute.py --kind fadd4 --lengths 0,4096,16384,65536 --count 32 --repeats 8 --device "$(DEVICE)" --output "$(DRMDIR)-fadd4"
	$(PYTHON) -B scripts/run_drm_compute.py --kind iadd8 --lengths 0,16384,32768 --count 32 --repeats 6 --device "$(DEVICE)" --output "$(DRMDIR)-iadd8"

LOG ?= results/2026-10-10-opcode-scan-kernel-log/gpu-lines.log.gz
grid-cap:
	for k in 16 17 18 19 20 21 22 23 24; do \
	  AGX_GLOBAL_Y=$$(( (1 << k) / 32 )) $(PYTHON) -B scripts/run_drm_compute.py --kind control --count 32 --repeats 2 --device "$(DEVICE)" --output "$(DRMDIR)-grid-y$$k" || exit 1; \
	  $(PYTHON) -B scripts/run_drm_compute.py --kind control --count $$((1 << k)) --repeats 2 --device "$(DEVICE)" --output "$(DRMDIR)-grid-x$$k" || exit 1; \
	done

grid-coverage:
	$(PYTHON) -B scripts/run_drm_grid_coverage.py --log2 16,18,20,22,24,26,28,30 --device "$(DEVICE)"

verify-alu-bitflip:
	$(PYTHON) -B scripts/verify_alu_bitflip.py

verify-fmadd-decode:
	$(PYTHON) -B scripts/verify_fmadd_decode.py

verify-fmadd-lane:
	$(PYTHON) -B scripts/replay_fmadd_lane.py

verify-subop-spaces:
	$(PYTHON) -B scripts/verify_subop_spaces.py

drm-limits:
	mkdir -p "$(SCRATCH_ROOT)/drm-limits"
	$(CC) -std=c11 -O2 -Wall -Wextra -Werror tests/drm_limits.c -o "$(SCRATCH_ROOT)/drm-limits/drm_limits"
	"$(SCRATCH_ROOT)/drm-limits/drm_limits" "$(DEVICE)" | tee "$(SCRATCH_ROOT)/drm-limits/out.jsonl"

drm-sync:
	$(PYTHON) -B scripts/run_drm_sync.py --modes 0,1,2 --repeats 16 --delay 4000 --device "$(DEVICE)"

submit-latency:
	$(PYTHON) -B scripts/run_drm_submit_latency.py --device "$(DEVICE)"

verify-submit-latency:
	$(PYTHON) -B scripts/verify_submit_latency.py

commands-per-submit:
	$(PYTHON) -B scripts/run_drm_cmds.py --device "$(DEVICE)"
	sleep 3
	$(PYTHON) -B scripts/run_drm_cmds.py --kinds delay --barriers none --ns 64 --repeats 16 --device "$(DEVICE)"

verify-commands-per-submit:
	$(PYTHON) -B scripts/verify_commands_per_submit.py

queue-priority:
	$(PYTHON) -B scripts/run_drm_priority.py --a-count 4194304 --a-repeats 64 --b-repeats 48 --device "$(DEVICE)"
	$(PYTHON) -B scripts/run_drm_priority.py --a-count 1048576 --a-delay 20000 --a-repeats 48 --b-repeats 48 --device "$(DEVICE)"
	$(PYTHON) -B scripts/run_drm_priority.py --a-count 1048576 --a-delay 20000 --a-local 128 --a-repeats 48 --b-repeats 48 --device "$(DEVICE)"

verify-queue-priority:
	$(PYTHON) -B scripts/verify_queue_priority.py

queue-concurrency:
	$(PYTHON) -B scripts/run_drm_queues.py --device "$(DEVICE)"

verify-queue-concurrency:
	$(PYTHON) -B scripts/verify_queue_concurrency.py

fixed18-waits:
	$(PYTHON) -B scripts/clock_keeper.py --seconds 600 --device "$(DEVICE)" & sleep 3; \
	cd scripts && CONFIRM_GPU_FAULTS=1 $(PYTHON) -B run_drm_sync_probe.py --suite wait18 --times 2 --repeats 24 --device "$(DEVICE)"; \
	touch /scratch/apple-m2-playground/drm-compute/keeper/stop

verify-fixed18-waits:
	$(PYTHON) -B scripts/verify_fixed18_waits.py

cache-line:
	$(PYTHON) -B scripts/clock_keeper.py --seconds 1500 --device "$(DEVICE)" & sleep 3; \
	$(PYTHON) -B scripts/run_drm_neighbour.py --device "$(DEVICE)"; \
	touch /scratch/apple-m2-playground/drm-compute/keeper/stop

verify-cache-line:
	$(PYTHON) -B scripts/verify_cache_line.py

verify-l2-command-boundary:
	$(PYTHON) -B scripts/verify_l2_command_boundary.py

verify-memory-parameters:
	$(PYTHON) -B scripts/verify_memory_parameters.py

cpu-gpu-visibility:
	$(PYTHON) -B scripts/run_drm_visibility.py --n 4096 --trials 4 --device "$(DEVICE)"

verify-cpu-gpu-visibility:
	$(PYTHON) -B scripts/verify_cpu_gpu_visibility.py

SIMREPO ?= $(abspath ../AGX-Performance-Simulator)

atomic-variants:
	@test "$(CONFIRM_GPU_FAULTS)" = 1 || { echo 'atomic-variants runs device-atomic encodings Mesa never emits (each first checked with a surrogate in agx_run); re-run with CONFIRM_GPU_FAULTS=1 on an idle machine.'; exit 1; }
	for f in A B D E F G H I; do $(PYTHON) -B $(SIMREPO)/scripts/probe_atomics.py run --family $$f --out /scratch/apple-m2-playground/atomic-variants || exit 1; done
	$(PYTHON) -B $(SIMREPO)/scripts/probe_atomics.py analyse /scratch/apple-m2-playground/atomic-variants

verify-atomic-variants:
	$(PYTHON) -B scripts/verify_atomic_variants.py

.PHONY: replay-atomic-variants
replay-atomic-variants:
	$(PYTHON) -B scripts/replay_atomic_variants.py --run "$(SIMREPO)/rust/target/release/agx_run"

INTEGER_ATOMIC_SUITE ?= $(SIMREPO)/testsuite
.PHONY: replay-integer-atomic-suite
replay-integer-atomic-suite:
	"$(SIMREPO)/rust/target/release/suite_check" "$(INTEGER_ATOMIC_SUITE)" --only atomic -v
	"$(SIMREPO)/rust/target/release/suite_check" "$(INTEGER_ATOMIC_SUITE)" --only tg_atomic -v

GEOMETRY_SUITE ?= $(SIMREPO)/testsuite
.PHONY: replay-geometry-suite
replay-geometry-suite:
	"$(SIMREPO)/rust/target/release/suite_check" "$(GEOMETRY_SUITE)" --only geometry -v

.PHONY: verify-simulator-launch
verify-simulator-launch:
	$(PYTHON) -B scripts/check_simulator_launch.py --run "$(SIMREPO)/rust/target/release/agx_dispatch"

.PHONY: verify-simulator-geometry
verify-simulator-geometry:
	$(PYTHON) -B scripts/check_simulator_geometry.py --run "$(SIMREPO)/rust/target/release/agx_run"

.PHONY: replay-simulator-sr
replay-simulator-sr:
	AGX_RUN="$(SIMREPO)/rust/target/release/agx_run" $(PYTHON) -B "$(SIMREPO)/scripts/sr_check.py"

.PHONY: replay-simulator-cost-sr
replay-simulator-cost-sr:
	$(PYTHON) -B scripts/replay_cost_sr.py --simrepo "$(SIMREPO)" --selftest

# Retained device loads/stores and threadgroup layout cases live in the simulator.
MEMORY_SUITE ?= $(SIMREPO)/testsuite
.PHONY: replay-memory-suite
replay-memory-suite:
	"$(SIMREPO)/rust/target/release/suite_check" "$(MEMORY_SUITE)" --only mem_load -v
	"$(SIMREPO)/rust/target/release/suite_check" "$(MEMORY_SUITE)" --only mem_store -v
	"$(SIMREPO)/rust/target/release/suite_check" "$(MEMORY_SUITE)" --only threadgroup -v

CONTROL_SUITE ?= $(SIMREPO)/testsuite
.PHONY: replay-control-suite
replay-control-suite:
	"$(SIMREPO)/rust/target/release/suite_check" "$(CONTROL_SUITE)" --only control -v

CROSS_LANE_SUITE ?= $(SIMREPO)/testsuite
.PHONY: replay-cross-lane-suite
replay-cross-lane-suite:
	"$(SIMREPO)/rust/target/release/suite_check" "$(CROSS_LANE_SUITE)" --case-prefix simd_ -v
	"$(SIMREPO)/rust/target/release/suite_check" "$(CROSS_LANE_SUITE)" --case-prefix quad_ -v
	"$(SIMREPO)/rust/target/release/suite_check" "$(CROSS_LANE_SUITE)" --case-prefix icmp_quad_ballot -v
	"$(SIMREPO)/rust/target/release/suite_check" "$(CROSS_LANE_SUITE)" --case-prefix fcmp_quad_ballot -v

atomic-contention:
	$(PYTHON) -B scripts/clock_keeper.py --seconds 3000 --device "$(DEVICE)" & sleep 3; \
	$(PYTHON) -B scripts/run_drm_atomic_contend.py --device "$(DEVICE)"; \
	touch /scratch/apple-m2-playground/drm-compute/keeper/stop

verify-atomic-contention:
	$(PYTHON) -B scripts/verify_atomic_contention.py

verify-drm-interface:
	$(PYTHON) -B scripts/verify_drm_interface.py

verify-cross-lane-width:
	$(PYTHON) -B scripts/verify_cross_lane_width.py

verify-battery-clock-states:
	$(PYTHON) -B scripts/verify_battery_clock_states.py

verify-mem-control-bitflip:
	$(PYTHON) -B scripts/verify_mem_control_bitflip.py

gpu-faults:
	$(PYTHON) -B scripts/summarize_gpu_faults.py "$(LOG)"

agx-loop-test:
	$(PYTHON) -B tests/test_agx_loop.py --hardware

verify-loops:
	$(PYTHON) -B scripts/verify_agx_loops.py

LOOPDIR = $(SCRATCH_ROOT)/drm-compute/runs/loops-$$(date -u +%Y%m%dT%H%M%SZ)
agx-loops:
	@for k in iadd8 fadd4; do for c in 1 2 4; do for m in 0 64; do \
	  $(PYTHON) -B scripts/run_drm_compute.py --kind loop --loop-kind $$k --chains $$c --steps $$m --lengths 2000 --count 32 --repeats 6 --device "$(DEVICE)" --output "$(LOOPDIR)-$$k-c$$c-m$$m" || exit 1; \
	done; done; done
	@for c in 1 2; do $(PYTHON) -B scripts/run_drm_compute.py --kind loop --loop-kind fadd4 --chains $$c --steps 512 --lengths 2000 --count 32 --repeats 40 --timeout 120 --device "$(DEVICE)" --output "$(LOOPDIR)-warm-fadd4-c$$c" || exit 1; done
	@for n in 32 1216 4864 9728 19456 38912; do $(PYTHON) -B scripts/run_drm_compute.py --kind loop --loop-kind fadd4 --chains 2 --steps 512 --lengths 2000 --count $$n --repeats 30 --timeout 120 --device "$(DEVICE)" --output "$(LOOPDIR)-groups-$$n" || exit 1; done

MEMDIR = $(SCRATCH_ROOT)/drm-compute/runs/memory-$$(date -u +%Y%m%dT%H%M%SZ)
agx-memory:
	$(PYTHON) -B scripts/run_drm_compute.py --kind chase --lengths 2048,4096,8192,12288,16384,24576,32768,49152,65536,131072,262144,524288,1048576,2097152,4194304,8388608,16777216,33554432,67108864,134217728,268435456 --steps 16 --trips 1000 --count 32 --repeats 30 --timeout 300 --device "$(DEVICE)" --output "$(MEMDIR)-fine"
	$(PYTHON) -B scripts/run_drm_compute.py --kind chase --stride 16384 --lengths 262144,1048576,4194304,16777216,33554432,67108864,134217728,268435456 --steps 16 --trips 1000 --count 32 --repeats 12 --timeout 300 --device "$(DEVICE)" --output "$(MEMDIR)-pages"

verify-memory:
	$(PYTHON) -B scripts/verify_agx_memory.py

agx-bandwidth:
	@for c in 1 2 4 8 16; do $(PYTHON) -B scripts/run_drm_compute.py --kind chase --chains $$c --gprs 48 --lengths 4194304,268435456 --steps 8 --trips 500 --count 32 --repeats 16 --timeout 300 --device "$(DEVICE)" --output "$(MEMDIR)-overlap-c$$c" || exit 1; done
	@for spec in "1216 6898" "4864 1724" "9728 862" "19456 431" "38912 215" "65536 128"; do set -- $$spec; \
	  $(PYTHON) -B scripts/run_drm_compute.py --kind stream --steps 8 --lengths $$2 --count $$1 --gprs 32 --repeats 12 --timeout 120 --device "$(DEVICE)" --output "$(MEMDIR)-stream-$$1" || exit 1; done

SRDIR = $(SCRATCH_ROOT)/drm-compute/sr-scan/make-$$(date -u +%Y%m%dT%H%M%SZ)
sr-direct:
	$(PYTHON) -B scripts/run_drm_sr_scan.py --device "$(DEVICE)" --output "$(SRDIR)" --configs base,base-repeat,lanes-96,local-64,helper-data,helper-cfg,priority-low,usc-moved,cdm-moved,words-only,code-only,words-0x8040,words-0x40,local-96,local-128,local-256,local-1024,shape-16x4,shape-8x8,shape-32x2x2,shape-4x8x4,order-shru,order-rhsu,order-ushnr,preshader-stop,preshader-first,samplers-4,word0-uniform-2,word0-texture-8,word0-preshader-16,occupancy-2048wg,occupancy-512x128,pre-control,pre-chunk0,pre-chunk1,pre-chunk0-local128,pre-chunk0-2048wg,atomic-33,atomic-64,atomic-65536,pre-atomic-2wg,pre-atomic-512x128,pre-atomic-2048wg,shader-unk2-2,shared-32x32-s8,shared-32x16-s8,shared-16x16-s8,shared-32x32-s32,shared-32x32-st2,shared-32x32-st3,shared-32x32-st7,shared-32x32-st15,shared-32x32-st0,shared-32x32-samples2,shared-32x32-samples4

verify-sr-direct:
	$(PYTHON) -B scripts/verify_sr_direct.py

DESCDIR = $(SCRATCH_ROOT)/drm-compute/opcode-describe/make-$$(date -u +%Y%m%dT%H%M%SZ)
opcode-describe:
	@test "$(CONFIRM_GPU_FAULTS)" = 1 || { echo 'opcode-describe runs untested operand encodings of non-faulting opcodes; re-run with CONFIRM_GPU_FAULTS=1 on an idle machine.'; exit 1; }
	$(PYTHON) -B scripts/run_drm_opcode_describe.py --device "$(DEVICE)" --output "$(DESCDIR)-shape"
	$(PYTHON) -B scripts/run_drm_opcode_describe.py --suite timing --device "$(DEVICE)" --output "$(DESCDIR)-timing"

test-opcode-describe:
	@test "$(CONFIRM_GPU_FAULTS)" = 1 || { echo 'needs CONFIRM_GPU_FAULTS=1'; exit 1; }
	$(PYTHON) -B tests/test_opcode_describe.py --hardware

verify-opcode-describe:
	$(PYTHON) -B scripts/verify_opcode_describe.py

SYNCDIR = $(SCRATCH_ROOT)/drm-compute/sync-probe/make-$$(date -u +%Y%m%dT%H%M%SZ)
sync-probe:
	@test "$(CONFIRM_GPU_FAULTS)" = 1 || { echo 'needs CONFIRM_GPU_FAULTS=1'; exit 1; }
	@for s in barrier tgcheck endpend endfollow; do $(PYTHON) -B scripts/run_drm_sync_probe.py --suite $$s --device "$(DEVICE)" --output "$(SYNCDIR)-$$s" || exit 1; done
	@for s in memwait tgwait scope; do $(PYTHON) -B scripts/run_drm_sync_probe.py --suite $$s --trips 50000 --repeats 4 --device "$(DEVICE)" --output "$(SYNCDIR)-$$s" || exit 1; done
	$(PYTHON) -B scripts/run_drm_sync_probe.py --suite endcost --times 3 --device "$(DEVICE)" --output "$(SYNCDIR)-endcost"

test-sync-and-end:
	@test "$(CONFIRM_GPU_FAULTS)" = 1 || { echo 'needs CONFIRM_GPU_FAULTS=1'; exit 1; }
	$(PYTHON) -B tests/test_sync_and_end.py --hardware

verify-sync-and-end:
	cd scripts && $(PYTHON) -B verify_sync_and_end.py

BSDIR = $(SCRATCH_ROOT)/drm-compute/barrier-stress/make-$$(date -u +%Y%m%dT%H%M%SZ)
barrier-stress:
	@test "$(CONFIRM_GPU_FAULTS)" = 1 || { echo 'needs CONFIRM_GPU_FAULTS=1'; exit 1; }
	$(PYTHON) -B scripts/run_drm_barrier_stress.py --device "$(DEVICE)" --output "$(BSDIR)-matrix"
	@for d in 2 4; do $(PYTHON) -B scripts/run_drm_barrier_stress.py --dist $$d --sizes 256 --device "$(DEVICE)" --output "$(BSDIR)-dist$$d" || exit 1; done
	$(PYTHON) -B scripts/run_drm_barrier_stress.py --sizes 512,1024 --device "$(DEVICE)" --output "$(BSDIR)-large"
	$(PYTHON) -B scripts/run_drm_tg_capacity.py

test-barrier-stress:
	@test "$(CONFIRM_GPU_FAULTS)" = 1 || { echo 'needs CONFIRM_GPU_FAULTS=1'; exit 1; }
	$(PYTHON) -B tests/test_barrier_stress.py --hardware

verify-barrier-stress:
	$(PYTHON) -B scripts/verify_barrier_stress.py

test-tg-addressing:
	$(PYTHON) -B tests/test_tg_addressing.py --hardware

verify-tg-addressing:
	$(PYTHON) -B scripts/verify_tg_addressing.py

test-in-shader-clock:
	$(PYTHON) -B tests/test_in_shader_clock.py --hardware

verify-in-shader-clock:
	$(PYTHON) -B scripts/verify_in_shader_clock.py

test-atomics:
	$(PYTHON) -B scripts/run_drm_atomic.py && $(PYTHON) -B scripts/run_drm_tg_atomic.py

verify-atomics:
	$(PYTHON) -B scripts/verify_atomics.py

test-float-semantics:
	$(PYTHON) -B scripts/run_drm_float.py

verify-float-semantics:
	$(PYTHON) -B scripts/verify_float_semantics.py

test-int64:
	$(PYTHON) -B scripts/run_drm_int64.py && $(PYTHON) -B scripts/run_drm_pointer.py

verify-int64:
	$(PYTHON) -B scripts/verify_int64.py

test-occupancy:
	$(PYTHON) -B scripts/run_drm_occupancy.py --steps 8000 --local-x 128

verify-memory-hierarchy:
	$(PYTHON) -B scripts/verify_memory_hierarchy.py

verify-shared-memory-sync:
	$(PYTHON) -B scripts/verify_shared_memory_sync.py

verify-dispatch:
	$(PYTHON) -B scripts/verify_dispatch.py

verify-core-scaling:
	$(PYTHON) -B scripts/verify_core_scaling.py

verify-occupancy:
	$(PYTHON) -B scripts/verify_occupancy.py

test-memory-ordering:
	$(PYTHON) -B scripts/run_drm_litmus.py --repeats 1

verify-memory-ordering:
	$(PYTHON) -B scripts/verify_memory_ordering.py

test-sb-lb:
	$(PYTHON) -B scripts/run_drm_litmus_sb_lb.py --repeats 1

verify-sb-lb:
	$(PYTHON) -B scripts/verify_sb_lb.py

verify-sb-minimal:
	$(PYTHON) -B scripts/verify_sb_minimal.py

test-fence-contention:
	$(PYTHON) -B scripts/probe_fence_contention.py hardware --samples 1 --output /scratch/apple-m2-playground/drm-compute/fence-contention-smoke.json

verify-fence-contention:
	$(PYTHON) -B scripts/verify_fence_contention.py

verify-fixup-cost:
	$(PYTHON) -B scripts/verify_fixup_cost.py

test-atomic-release:
	$(PYTHON) -B scripts/run_drm_litmus_atomic.py --repeats 1

verify-atomic-release:
	$(PYTHON) -B scripts/verify_atomic_release.py

test-dispatch-visibility:
	$(PYTHON) -B scripts/run_drm_dispatch_visibility.py --repeats 1

verify-dispatch-visibility:
	$(PYTHON) -B scripts/verify_dispatch_visibility.py

verify-fence-cost:
	$(PYTHON) -B scripts/verify_fence_cost.py

verify-fence-model:
	$(PYTHON) -B scripts/verify_fence_model.py

verify-tg-litmus:
	$(PYTHON) -B scripts/verify_tg_litmus.py

verify-tg-end-scope:
	$(PYTHON) -B scripts/verify_tg_end_scope.py

verify-atomic-pairs:
	$(PYTHON) -B scripts/verify_atomic_pairs.py

verify-bfeil-verdict:
	$(PYTHON) -B scripts/verify_bfeil_verdict.py

verify-fcmp:
	$(PYTHON) -B scripts/verify_fcmp.py

verify-fcmp-extra:
	$(PYTHON) -B scripts/verify_fcmp_extra.py

verify-fcmp16:
	$(PYTHON) -B scripts/verify_fcmp16.py

verify-fcmp64:
	$(PYTHON) -B scripts/verify_fcmp64.py

verify-softfp64:
	$(PYTHON) -B scripts/verify_softfp64.py

verify-fp64-divsqrt:
	$(PYTHON) -B scripts/verify_fp64_divsqrt.py

verify-shfl:
	$(PYTHON) -B scripts/verify_shfl.py

.PHONY: verify-shfl-mask
verify-shfl-mask:
	$(PYTHON) -B scripts/verify_shfl_mask.py

.PHONY: verify-empty-stop
verify-empty-stop:
	$(PYTHON) -B scripts/verify_empty_stop.py

.PHONY: verify-ret-winner
verify-ret-winner:
	$(PYTHON) -B scripts/verify_ret_winner.py

.PHONY: verify-call-winner
verify-call-winner:
	$(PYTHON) -B scripts/verify_call_winner.py

.PHONY: verify-sparse-control
verify-sparse-control:
	$(PYTHON) -B scripts/verify_sparse_control.py

.PHONY: verify-control-model
verify-control-model:
	$(PYTHON) -B scripts/verify_measured_control_model.py

.PHONY: verify-call-r1
verify-call-r1:
	$(PYTHON) -B scripts/verify_call_r1.py

.PHONY: verify-three-targets
verify-three-targets:
	$(PYTHON) -B scripts/verify_three_targets.py

.PHONY: verify-ret-mask-state
verify-ret-mask-state:
	$(PYTHON) -B scripts/verify_ret_mask_state.py

verify-occupancy2:
	$(PYTHON) -B scripts/verify_occupancy2.py

verify-clock2:
	$(PYTHON) -B scripts/verify_clock2.py

verify-clock-model:
	$(PYTHON) -B scripts/verify_clock_model.py

verify-atom64:
	$(PYTHON) -B scripts/verify_atom64.py

verify-preshader:
	$(PYTHON) -B scripts/verify_preshader.py

verify-stack-mesa:
	$(PYTHON) -B scripts/verify_stack_mesa.py

verify-fmadd-followups:
	$(PYTHON) -B scripts/verify_fmadd_followups.py

verify-fma-b52:
	$(PYTHON) -B scripts/verify_fma_b52.py

verify-slc:
	$(PYTHON) -B scripts/verify_slc.py

verify-imageblock-occ:
	$(PYTHON) -B scripts/verify_imageblock_occ.py

verify-gles-texture:
	$(PYTHON) -B scripts/verify_gles_texture.py

verify-texture-edge:
	$(PYTHON) -B scripts/verify_texture_edge.py

verify-texture-targets:
	$(PYTHON) -B scripts/verify_texture_targets.py

verify-texture-unit:
	$(PYTHON) -B scripts/verify_texture_unit.py

verify-spill-cost:
	$(PYTHON) -B scripts/verify_spill_cost.py

verify-sincos-cost:
	$(PYTHON) -B scripts/verify_sincos_cost.py

verify-barrier-cost:
	$(PYTHON) -B scripts/verify_barrier_cost.py

bench:
	$(PYTHON) -B scripts/run_bench.py --modes latency,simd_issue,gpu

verify-bench:
	$(PYTHON) -B scripts/verify_bench.py

.PHONY: capture-demo
capture-demo:
	mkdir -p "$(SCRATCH_ROOT)/capture/demo"
	$(CC) -std=c11 -O2 -I"$(PROBE_INCLUDE)" tests/gles_compute.c -o "$(SCRATCH_ROOT)/capture/demo/gles_compute" -ldl
	$(PYTHON) -B scripts/agx_capture.py --ir --out "$(SCRATCH_ROOT)/capture/demo" -- "$(SCRATCH_ROOT)/capture/demo/gles_compute" private 64 $(DEVICE)

verify-special-registers:
	$(PYTHON) -B scripts/verify_special_registers.py

sr-vm-slot:
	$(PYTHON) -B scripts/run_sr_vm_slot.py --concurrent 16 --sequential 70 --repeats 10

sr-divergence:
	$(PYTHON) -B scripts/run_sr_divergence.py

sr113-reps:
	$(PYTHON) -B scripts/run_sr113_reps.py

sr113-timeline:
	$(PYTHON) -B scripts/run_sr113_reps.py --timeline --chase 1000 --trials 30 --reps 64
	for us in 0 1000 2000 3000; do $(PYTHON) -B scripts/run_sr113_reps.py --timeline --chase 1000 --trials 8 --reps 64 --rep-sleep-us $$us || exit 1; done

verify-transcendentals:
	$(PYTHON) -B scripts/verify_transcendentals.py


.PHONY: verify-call-ret
verify-call-ret:
	$(PYTHON) -B scripts/verify_call_ret.py

.PHONY: verify-atomic-gap-bits
verify-atomic-gap-bits:
	$(PYTHON) -B scripts/verify_atomic_gap_bits.py

.PHONY: verify-tg-atomic-followup test-probe-watchdog
verify-tg-atomic-followup:
	$(PYTHON) -B scripts/verify_tg_atomic_followup.py

test-probe-watchdog:
	$(PYTHON) -B scripts/test_probe_watchdog.py

.PHONY: verify-empty-ret-state
verify-empty-ret-state:
	$(PYTHON) -B scripts/verify_empty_ret_state.py

.PHONY: verify-masked-r0
verify-masked-r0:
	$(PYTHON) -B scripts/verify_masked_r0.py

.PHONY: verify-stopped-r0
verify-stopped-r0:
	$(PYTHON) -B scripts/verify_stopped_r0.py

.PHONY: verify-stopped-shuffle-index
verify-stopped-shuffle-index:
	$(PYTHON) -B scripts/verify_stopped_shuffle_index.py

.PHONY: verify-dead-index-or
verify-dead-index-or:
	$(PYTHON) -B scripts/verify_dead_index_or.py

.PHONY: verify-stopped-native-shuffle
verify-stopped-native-shuffle:
	$(PYTHON) -B scripts/verify_stopped_native_shuffle.py

.PHONY: verify-native-dead-index-or
verify-native-dead-index-or:
	$(PYTHON) -B scripts/verify_native_dead_index_or.py

.PHONY: verify-nested-divergent
verify-nested-divergent:
	$(PYTHON) -B scripts/verify_nested_divergent.py

.PHONY: verify-nested-early-return
verify-nested-early-return:
	$(PYTHON) -B scripts/verify_nested_early_return.py

.PHONY: verify-nested-partial-outer
verify-nested-partial-outer:
	$(PYTHON) -B scripts/verify_nested_partial_outer.py

.PHONY: verify-call-mask-reserve
verify-call-mask-reserve:
	$(PYTHON) -B scripts/verify_call_mask_reserve.py

.PHONY: verify-deep-call-reserve
verify-deep-call-reserve:
	$(PYTHON) -B scripts/verify_deep_call_reserve.py

.PHONY: verify-deep-ret-counters
verify-deep-ret-counters:
	$(PYTHON) -B scripts/verify_deep_ret_counters.py

.PHONY: verify-r0-write-mask
verify-r0-write-mask:
	$(PYTHON) -B scripts/verify_r0_write_mask.py

.PHONY: verify-r0-pop0
verify-r0-pop0:
	$(PYTHON) -B scripts/verify_r0_pop0.py

.PHONY: verify-ret-stale-exec
verify-ret-stale-exec:
	$(PYTHON) -B scripts/verify_ret_stale_exec.py

.PHONY: verify-wide-r0
verify-wide-r0:
	$(PYTHON) -B scripts/verify_wide_r0.py

.PHONY: verify-ret-stale-targets
verify-ret-stale-targets:
	$(PYTHON) -B scripts/verify_ret_stale_targets.py

.PHONY: verify-overflow-first-shuffle
verify-overflow-first-shuffle:
	$(PYTHON) -B scripts/verify_overflow_first_shuffle.py

.PHONY: verify-overflow-register-visibility
verify-overflow-register-visibility:
	$(PYTHON) -B scripts/verify_overflow_register_visibility.py

.PHONY: verify-overflow-guard
verify-overflow-guard:
	$(PYTHON) -B scripts/verify_overflow_guard.py

.PHONY: verify-integer-chain-cost
verify-integer-chain-cost:
	$(PYTHON) -B scripts/verify_integer_chain_cost.py

.PHONY: verify-integer-chain-train test-integer-chain-train
verify-integer-chain-train:
	$(PYTHON) -B scripts/verify_integer_chain_train.py

test-integer-chain-train:
	$(PYTHON) -B scripts/test_integer_chain_train.py

.PHONY: verify-integer-immediate-cost
verify-integer-immediate-cost:
	$(PYTHON) -B scripts/verify_integer_immediate_cost.py

.PHONY: verify-integer-timing-state
verify-integer-timing-state:
	$(PYTHON) -B scripts/verify_integer_timing_state.py

.PHONY: verify-integer-length-cost
verify-integer-length-cost:
	$(PYTHON) -B scripts/verify_integer_length_cost.py

.PHONY: verify-integer-core-distribution test-integer-core-distribution
verify-integer-core-distribution:
	$(PYTHON) -B scripts/verify_integer_core_distribution.py

test-integer-core-distribution:
	$(PYTHON) -B scripts/test_integer_core_distribution.py

.PHONY: verify-integer-geometry-cost test-integer-geometry-cost
verify-integer-geometry-cost:
	$(PYTHON) -B scripts/verify_integer_geometry_cost.py

test-integer-geometry-cost:
	$(PYTHON) -B scripts/test_integer_geometry_cost.py

.PHONY: verify-observed-core-map-replay
verify-observed-core-map-replay:
	$(PYTHON) -B scripts/verify_observed_core_map_replay.py

.PHONY: verify-observed-core-map-tracing
verify-observed-core-map-tracing:
	$(PYTHON) -B scripts/verify_observed_core_map_tracing.py

.PHONY: verify-observed-core-map-cost
verify-observed-core-map-cost:
	$(PYTHON) -B scripts/verify_observed_core_map_cost.py
