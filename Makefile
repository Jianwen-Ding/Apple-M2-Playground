PYTHON ?= python3
SCRATCH_ROOT ?= /scratch/apple-m2-playground
DEVICE ?= /dev/dri/renderD128
PROBE_INCLUDE ?= /save/workspace/AGX_Probe/mesa/include
APPLEGPU_ROOT ?= /save/workspace/AGX_Probe/applegpu
MESA_ROOT ?= /save/workspace/AGX_Probe/mesa
export CC PROBE_INCLUDE

.PHONY: help env check smoke params time compute instruction-candidates agx-instruction agx-imadd verify-imadd

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
