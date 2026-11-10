# workgroup placement: 1 resident workgroup per core (threadgroup memory 40000 B), fixed work per workgroup;
# does a 38-workgroup grid put two on one core (time doubles vs 30-36)?
cd /scratch/agx-r5/place
H=/scratch/agx-r5/zcopy/target/release/agx_run_hw
for n in 1 19 30 34 36 37 38 39 40 76 77; do
  /scratch/agx-r5/waitidle.sh 5
  r=$($H k.bin --grid $((n*128)),1,1 --wg 128,1,1 --regs 64 --shared 40000 --uniform 5=200 --uniform 6=0 --uniform 8=0 --uniform 9=17 --alloc 0x1100000000=65536 --back-to-back 1000 --timeout-ms 10000 | grep -o '"b2b_median_fw_ns":[0-9]*')
  echo "wgs $n $r"
done
