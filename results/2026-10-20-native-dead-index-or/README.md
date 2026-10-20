# Native stopped index-bit contribution evidence

320 compressed records: four native forms, both alternating stop masks, four
initial low seeds and ten new boundary offsets. Each has exact wait controls
before and after: 960 dispatches, zero faults. The initial offset-2/seed-1 case
of every form was inspected separately before matrix submission.

Exact code/input/readbacks, source/harness hashes, current-model hypotheses,
firmware samples, diagnostic/recovery metadata and competing retained/excluded
index classifications are retained. Layout follows the 240-word paired-index
probes. All inputs are initialized within the same shader before divergence
or stop. Run `make verify-native-dead-index-or` for reconstruction, source
provenance, independent full-buffer oracles and simulator gap accounting.
See the [finding](../../novel-results/2026-10-20-native-dead-index-or/README.md).
