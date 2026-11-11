# sim agent: atomic collision probe (scripts/probe_atomic_lines.py), hw + sim
cd /save/workspace/AGX-Performance-Simulator/scripts; export AGX_RUN_HW=/scratch/agx-r5/zcopy/target/release/agx_run_hw
O=/scratch/agx-r5/r10/atom1.txt
{ T=2000 PAT="0:1 31:1 15:1 7:1 3:1 1:1 7:2 3:16 1:16 31:16 3:4" python3 probe_atomic_lines.py both
  T=2000 PERWG=1 PAT="0:1 3:1 31:1" python3 probe_atomic_lines.py both
  T=500 G=4 PAT="0:1 3:1 31:1 3:16" python3 probe_atomic_lines.py both
  T=2000 NWG=1 PAT="0:1 3:1 31:1" python3 probe_atomic_lines.py both
  T=2000 NWG=8 PAT="0:1 3:1" python3 probe_atomic_lines.py both; } > $O 2>&1
