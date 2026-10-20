# sqrt.f32 evidence (2026-10-20)

`record.json.gz`: `hw-<seq>` (exhaustive [1, 4)), `hw-<seq>-sweep` (all exponents × 65,536 mantissas): input count,
mismatch count against the integer-isqrt reference, ulp histogram (flush-sized deltas dropped), and mismatches per exponent.
`cost/<seq>-k<K>`: clock-held chain timings. Check: `make verify-fsqrt32`. Full output arrays are not retained (64 MB each).
