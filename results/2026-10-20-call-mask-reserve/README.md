# Balanced call-mask reserve evidence

192 compressed records: two outer forms, four prefix lengths, three inner
winners, two seeds and four outer/inner reserve pairs. Each has exact no-call
controls before/after: 576 dispatches, zero faults. Initial four reserve-pair
cases were inspected individually. Every shader/input/readback, source/harness
hash, complete-model gate, decoded boundary, firmware sample and diagnostic/
recovery datum is preserved unchanged.

The 624-word table extends partial-outer traces: plane 15 is original mask
input, plane 16 final full-group marker after original-IF pop, plane 17 final
r1, plane 18 direct low r0 gather from initialized original excluded lane 0,
then 16 guards. Source upper bits are masked away; only immediate index 0 is
used. The final bounded drain occurs after these diagnostics. Function target
addresses stay fixed and both links are recomputed after reserve insertion.

`make verify-call-mask-reserve` reconstructs exact code, resolves hashes,
checks link formulas and independently checks every output word, including
0/3/5 direct masked counters and original caller participation. See the
[finding](../../novel-results/2026-10-20-call-mask-reserve/README.md).
