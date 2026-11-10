# one resident workgroup per core because of its size (1024 threads, no threadgroup memory) vs because of memory
cd /scratch/agx-r5/place
H=/scratch/agx-r5/zcopy/target/release/agx_run_hw
for n in 1 34 35 38 39; do
  /scratch/agx-r5/waitidle.sh 5
  r=$($H k.bin --grid $((n*1024)),1,1 --wg 1024,1,1 --regs 64 --uniform 5=50 --uniform 6=0 --uniform 8=0 --uniform 9=17 --alloc 0x1100000000=65536 --back-to-back 1000 --timeout-ms 10000 | grep -o '"b2b_median_fw_ns":[0-9]*')
  echo "wg1024 wgs $n $r"
done
