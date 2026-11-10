# GPU clock ladder vs CPU load: the dependent-iadd probe (t350: ~20 us at the top state, 38 workgroups), b2b 1000,
# per-command trace; idle CPU / 10 busy CPU threads / idle again
cd /scratch/agx-r5
for phase in idle1 busy idle2; do
  pids=""
  if [ $phase = busy ]; then for i in $(seq 10); do (while :; do :; done) & pids="$pids $!"; done; sleep 5; fi
  /scratch/agx-r5/waitidle.sh 10
  for r in 0 1; do
    IDLE_S=3 python3 clock.py 350 1000 -1 38 1 && mv clock/t350-n1000-g-1-w38-0.txt clock/cpu-$phase-$r.txt
  done
  [ -n "$pids" ] && kill $pids
  cat /sys/class/hwmon/hwmon1/power1_input 2>/dev/null
done
for f in clock/cpu-*.txt; do echo $f $(awk '{print $2-$1}' $f | tail -500 | sort -n | awk '{a[NR]=$1} END{print "median", a[int(NR/2)], "p10", a[int(NR/10)]}'); done
