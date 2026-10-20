# Core distribution in arithmetic timing trains

2026-10-20, before hardware. The length study retains a broad timing shortfall
against the model's 38-core launch assumption. Use established SR19 and SR20
reads to distinguish a fixed allocation tag from actual final-dispatch core
placement, preserving arithmetic values and the same output-plane footprint.

Append a tag plane after the existing arithmetic planes. Matched candidate
twins differ only in the selector of one four-byte get_sr into r30: SR19
must give 64 allocated register halves, while SR20 gives `(cluster<<4)|core`.
The register allocation stays 64 halves; arithmetic registers and body remain
unchanged. Every core tag must be valid under masks 3ff/1ff/1ff/3ff and uniform
within each workgroup. Count workgroups per core and cluster, retaining all
tags. Do not assume equal or exact placement in the hardware oracle.

The scalar oracle checks all arithmetic words, guards and SR19 tags exactly.
Default-placement simulation must also match all SR20 tags as zero, and pass
the hardware property checker. These are separate claims: physical core tags
are not expected to equal default simulator placement. Simulate successive
output-only table states. Zero-add SR19 controls bracket every train.

First test 32 lanes / 4096 adds / four submissions for each 1/8-chain and
SR19/SR20 combination. After complete buffer checks and exact recovery,
prepare full gates for 131072 lanes, workgroups of 128, 1024/4096 adds,
1/8 chains and both selectors. Run three interleaved trials, each with 64
submissions and the established 1000 us host delay. Use one worker, bounded
waits and process watchdog, source/binary and kernel/memory/power diagnostics,
and stop after a blocked process or failed recovery. Preserve every timestamp
and final buffer. Core maps describe only the final dispatch; intermediate
buffers and simultaneous residency are not measured.

Completed: 28 trains / 1608 dispatches, exact arithmetic/guards and all 56
recovery controls, valid complete SR20 maps, zero faults. All full-size core
maps contain 38 IDs, with busiest-core counts 28–33. See the
[finding](../../novel-results/2026-10-20-integer-core-distribution/README.md).
