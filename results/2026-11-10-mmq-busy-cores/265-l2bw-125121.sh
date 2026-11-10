# GPU-wide bandwidth of the level below L1 (MMQ: 17 -> 34 cores costs +21-29% per workgroup on hw): 32 groups per core
# streaming a 64-256 KB per-core region, 8 / 17 / 34 cores (one workgroup each; 17 = clusters 0-1 + 1)
export AGX_RUN_HW=/scratch/agx-r5/zcopy/target/release/agx_run_hw B2B=500
/scratch/agx-r5/waitidle.sh 5
cd /save/workspace/AGX-Performance-Simulator
WG=1024 T=1000 N="1 8 17 34" REGKB="64 256 1024" python3 scripts/probe_l2_share.py hw
