PYTHON ?= python3
SCRATCH_ROOT ?= /scratch/apple-m2-playground
DEVICE ?= /dev/dri/renderD128
PROBE_INCLUDE ?= /save/workspace/AGX_Probe/mesa/include
APPLEGPU_ROOT ?= /save/workspace/AGX_Probe/applegpu
MESA_ROOT ?= /save/workspace/AGX_Probe/mesa
export CC PROBE_INCLUDE

.PHONY: help env check smoke params time compute instruction-candidates agx-instruction agx-imadd verify-imadd sr-scan sr-pairs sr-characterize sr-even sr-context verify-sr sr-shape sr-core sr-alt sr-alt-reread sr-std-preload verify-sr-shape sr-shared sr-meta sr-width verify-sr-resources opcode-scan timestamps verify-timestamps drm-compute grid-cap grid-coverage verify-alu-bitflip verify-subop-spaces verify-mem-control-bitflip gpu-faults agx-loop-test verify-loops agx-loops agx-memory verify-memory agx-bandwidth sr-direct verify-sr-direct opcode-describe test-opcode-describe verify-opcode-describe sync-probe test-sync-and-end verify-sync-and-end barrier-stress test-barrier-stress verify-barrier-stress test-tg-addressing verify-tg-addressing test-in-shader-clock verify-in-shader-clock test-atomics verify-atomics test-float-semantics verify-float-semantics test-int64 verify-int64 test-occupancy verify-occupancy

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
	@echo 'make verify-subop-spaces Verify funop/iunop/simd_op/shuffle sub-op sweeps offline'
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

verify-subop-spaces:
	$(PYTHON) -B scripts/verify_subop_spaces.py

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

verify-occupancy:
	$(PYTHON) -B scripts/verify_occupancy.py
