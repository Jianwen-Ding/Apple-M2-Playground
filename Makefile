PYTHON ?= python3
SCRATCH_ROOT ?= /scratch/apple-m2-playground
DEVICE ?= /dev/dri/renderD128

.PHONY: help env check smoke

help:
	@echo 'make env    Capture environment metadata without opening the GPU'
	@echo 'make check  Check Python and C syntax without opening the GPU'
	@echo 'make smoke  Compile and run the DRM access test'
	@echo 'Override SCRATCH_ROOT, DEVICE, PYTHON, or the CC environment variable as needed.'

env:
	$(PYTHON) -B scripts/run.py env --scratch-root "$(SCRATCH_ROOT)"

check:
	$(PYTHON) -B scripts/run.py check --scratch-root "$(SCRATCH_ROOT)"

smoke:
	$(PYTHON) -B scripts/run.py drm-smoke --scratch-root "$(SCRATCH_ROOT)" --device "$(DEVICE)"
