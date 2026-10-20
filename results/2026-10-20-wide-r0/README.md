# Wide low-r0 counter evidence

The 36 gzip records retain exact candidate/control bytes, input and complete
output tables, assembler boundaries, simulator/builder/harness hashes,
firmware timestamps, watchdog/kernel/memory snapshots and pre/post recovery
controls. All records finished, all controls pass, event counts remain zero,
and the boot identity is unchanged. Recorded AC-online is 0, not 1.

`make verify-wide-r0` reconstructs bytes and independently calculates every
readback word for all three phases and both counter/payload banks. It checks
the bounded drain, target boundaries, controls without RET/pop0, guard regions,
and direct measured-model replay. Both rotations pass at every staged maximum.

`model-replay.json` binds the simulator binary/source hashes and all **2,313**
evidence-file digests. It replays saved original shader/input bytes directly,
without shader regeneration or GPU access. Every main/table buffer matches
simulator c7e50f7. No simulator implementation change was needed for this batch.

[Interpretation and limits](../../novel-results/2026-10-20-wide-r0/README.md).
