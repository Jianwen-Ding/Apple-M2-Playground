# Texture targets and filter precision evidence (2026-10-20)

Command: `python3 -B scripts/run_gles_texture_targets.py` (Mesa GLES compute; cases 15-19 were run with `--only`
into a second scratch directory and merged). `record.json.gz` holds every case's raw output words, `shaders/` the
GLSL, `listings/` the `scripts/agx_capture.py` disassembly of the Mesa shader cache.

Check: `make verify-texture-targets` (35/35 pass). Finding: [novel-results/2026-10-20-texture-targets](../../novel-results/2026-10-20-texture-targets/README.md).
Limits: one device, one Mesa build. The 3D 8-tap random-point residual (5/448) is recorded but not modelled.
