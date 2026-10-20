# Ordinary r0 write synchronization evidence

34 compressed records: three register-source forms with mixed maxima 1/3/31,
both rotations; all four forms with uniform depths 1/2/3/31. Exact no-r0-write
controls bracket each candidate: 102 dispatches, zero faults. Initial forms
were checked separately. Exact shaders/input/readbacks, source/harness hashes,
write-PC/encoding, whole-program gates, hypothesis/writer classifications,
firmware samples and diagnostics/recovery metadata are preserved unchanged.

The 176-word table contains 32 initialized input depths, prefix, immediate
post-write low-r0 snapshot, post-pop1 snapshot, final marker and 16 guards.
Every lane writes its new low counter before pop; only original 0/1 lanes
write after pop1. The control copies input to a GPR first and constructs
counters with IFs before the identical tail. `make verify-r0-write-mask`
reconstructs all bytes and independently checks exact values, lane sets,
write encodings, provenance and full simulator replay. See the
[finding](../../novel-results/2026-10-20-r0-write-mask/README.md).
