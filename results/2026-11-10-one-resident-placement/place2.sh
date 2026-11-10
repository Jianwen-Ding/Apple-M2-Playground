cd /scratch/agx-r5/place
H=/scratch/agx-r5/zcopy/target/release/agx_run_hw
for sh in 40000 20000; do for n in 35 36 70 71 72; do
  /scratch/agx-r5/waitidle.sh 5
  r=$($H k.bin --grid $((n*128)),1,1 --wg 128,1,1 --regs 64 --shared $sh --uniform 5=200 --uniform 6=0 --uniform 8=0 --uniform 9=17 --alloc 0x1100000000=65536 --back-to-back 1000 --timeout-ms 10000 | grep -o '"b2b_median_fw_ns":[0-9]*')
  echo "shared $sh wgs $n $r"
done; done
