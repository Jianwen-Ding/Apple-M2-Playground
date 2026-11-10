# MMQ Q5_K at 16 / 24 / 26 / 28 / 32 workgroups (clusters 0-1 / 0-2 / +cluster 3): where does the per-workgroup time jump?
export B2B=200 REP=2 AGX_CORE_CYCLE_BUDGET=1 AGX_PLACED_BUDGET=1
/scratch/agx-r5/waitidle.sh 5
cd /scratch/sim-captures/r5/llama-pp-fa0/311445-cap5293-* && python3 /scratch/agx-r5/gsweep.py . 512,8,1 768,8,1 832,8,1 896,8,1 1024,8,1 --hw
