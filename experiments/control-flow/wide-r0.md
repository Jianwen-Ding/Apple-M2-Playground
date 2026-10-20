# Wider execution counters from initialized ordinary writes

2026-10-20, before hardware. Ordinary writes and pop0 now have separate measured
low-depth behavior. `probe_wide_r0.py` seeds initialized low-r0 values in every
physical lane, synchronizes with pop0, and gathers every source's low counter
and payload before transfer, at a valid target, and after one pop1. Compare
an original-state jump with a uniform nonempty RET. Source high halves are
masked away; all indices are immediate and all inputs belong to this shader.

Known controls do not write wide counters, use pop0 or RET. They gather input
payload through ordinary GPRs using only simple known IF masks for original
zero lanes and original 0/1 lanes. Whole actual/control programs must match
independent scalar full-buffer oracles before any candidate. Every byte and
transfer/fallback/drain target decodes in-program. Fallthrough leaves a separate
marker and uses complementary conditional jumps into a bounded drain. No
loop/backedge, barrier, invalid target or uninitialized source is involved.

Candidate drain is unrolled pop3, ceil(maximum/3)+2 operations, after snapshots;
the largest planned program stays below the measured C harness 1 MiB shader
limit. This tests wider counter storage, zero-membership synchronization,
nonempty return and unsigned pop1 arithmetic together in isolated checkpoints.
Progress only after each exact recovered stage: maxima 63,255,511,1023,4095,
16383,32767,65534, then 65535 separately. The all-ones value is a distinct last
question, not assumed ordinary. First maximum63 original only, inspect all
words/recovery, then RET. Any mismatch pauses width escalation for analysis;
fault/hang logs and partial data are preserved. Failed recovery or a blocked
host process stops further GPU submissions. Rotate only after original stage
outcomes are understood. User-authorized unsafe policy remains in force.

Outcome: all 36 staged/rotated programs, 108 dispatches, exact full-buffer
readbacks and controls, zero faults. Numeric pop0 preservation, unsigned pop1
and deeper RET preservation hold at the sampled boundaries through 0xffff.
The all-ones source is still living/readable and rejoins after the drain.
Recorded AC-online is 0 throughout; no timing inference is made.
[Independent verification and scope](../../novel-results/2026-10-20-wide-r0/README.md).
