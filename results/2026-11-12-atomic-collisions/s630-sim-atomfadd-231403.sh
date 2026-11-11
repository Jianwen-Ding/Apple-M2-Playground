# sim agent: float atomic add collision probe + private-word (PERWG) cases
cd /save/workspace/AGX-Performance-Simulator/scripts; export AGX_RUN_HW=/scratch/agx-r5/zcopy/target/release/agx_run_hw
O=/scratch/agx-r5/r10/atom2.txt
{ FADD=1 T=1000 PAT="0:1 1:1 3:1 31:1 3:16 1:16" python3 probe_atomic_lines.py both
  FADD=1 T=1000 PERWG=1 PAT="0:1 3:1 31:1" python3 probe_atomic_lines.py both
  FADD=1 T=1000 NWG=1 PAT="0:1 31:1" python3 probe_atomic_lines.py both
  FADD=1 T=250 G=4 PERWG=1 PAT="0:1 3:1" python3 probe_atomic_lines.py both
  T=500 G=4 PERWG=1 PAT="0:1 3:1" python3 probe_atomic_lines.py both
  T=500 G=4 NWG=8 PERWG=1 PAT="0:1" python3 probe_atomic_lines.py both
  FADD=1 T=1000 NWG=8 PAT="0:1" python3 probe_atomic_lines.py both; } > $O 2>&1
