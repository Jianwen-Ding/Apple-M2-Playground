# sim agent: shade_background with its no-return atomics patched out (float only / all): hw
O=/scratch/agx-r5/r10/cyc/sbnoat.txt; : > $O
for v in float all; do d=$(ls -d /scratch/agx-r5/r10/var/sb-noat-$v/*-cap*)
 NOSIM=1 B2B=20 REP=3 python3 /scratch/agx-r5/gsweep.py $d 267520 --hw | sed "s|^|noat-$v |" >> $O
 NOSIM=1 B2B=3 REP=3 python3 /scratch/agx-r5/gsweep.py $d 12190400 --hw | sed "s|^|noat-$v |" >> $O
done
