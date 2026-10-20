# Native stopped-source shuffle evidence

160 compressed records: four native forms (down/up/xor/rotate-up), maximum
depths 1/3, rotations 0/1, offsets 0,1,2,3,4,7,8,15,16,31. Each record has exact
before/after wait controls: 480 dispatches, zero faults. Initial offset-1 cases
for each form were inspected separately. Tables use the 240-word paired-index
layout; all source payloads and index halves are initialized before masking.

Exact code, inputs, readbacks, source/harness hashes, current-model gates,
firmware samples, hypothesis classifications, diagnostics and recovery data
are preserved unchanged. The verifier reconstructs all bytes, resolves source
hashes and checks every output word against an independent per-lane oracle,
including source-liveness simulator counterexamples. Run
`make verify-stopped-native-shuffle`; see the
[finding](../../novel-results/2026-10-20-stopped-native-shuffle/README.md).
