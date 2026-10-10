PYTHON ?= python3
SCRATCH_ROOT ?= /scratch/apple-m2-playground
DEVICE ?= /dev/dri/renderD128
PROBE_INCLUDE ?= /save/workspace/AGX_Probe/mesa/include
APPLEGPU_ROOT ?= /save/workspace/AGX_Probe/applegpu
MESA_ROOT ?= /save/workspace/AGX_Probe/mesa
export CC PROBE_INCLUDE

.PHONY: help env check smoke params time compute instruction-candidates agx-instruction agx-imadd verify-imadd sr-scan sr-pairs sr-characterize sr-even sr-context verify-sr sr-shape sr-core sr-alt sr-alt-reread sr-std-preload verify-sr-shape sr-shared sr-meta sr-width verify-sr-resources

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
