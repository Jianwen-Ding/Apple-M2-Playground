# Empty/partial-mask stop and return-context evidence

Ten `empty-stop-*.json.gz` records and seven `ret-empty-stop-*.json.gz` records
retain every code/control byte, initialized table, complete main and table
readback, source/simulator hashes, simulator hypothesis, decoded boundaries,
firmware events, kernel delta, boot/budget, memory and recovery status.
Each record is one variant between two exact known-operation controls.

The table has six 32-word planes and 16 untouched guards: prefix marker,
partial-mask checkpoint (plain) or fallback marker (return), markers after
pops 1/2/3, and r0l after pop 3. Untouched words start as 0xcdcdcdcd. The main
output has its usual eight guards before/after payload and 16 patterned words.

`scripts/verify_empty_stop.py` independently derives checkpoint membership
sets, reconstructs the exact code, checks every hardware word and replays the
measured simulator model. Six records contradicted the original simulator;
the corrected return/stop model now reproduces all 17 exactly. Original
hypothesis source bytes remain archived under ret-prepop/source-before-model.
All three dispatch phases passed.

The shared unsafe harness imports `run_bench` from the adjacent simulator;
its C harness is **AGX-Performance-Simulator/tests/drm_compute.c**. Its actual
source hash is retained and checked. This is native direct DRM with no Mesa.
The verifier requires the adjacent `agx_run` and `agx_asm` release binaries.
See the [finding](../../novel-results/2026-10-20-empty-stop/README.md).
