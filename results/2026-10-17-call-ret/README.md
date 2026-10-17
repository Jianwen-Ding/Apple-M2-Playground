# Previous call / ret probes, retained 2026-10-17

`records.json.gz` preserves six JSON files from scratch, including their source
SHA-256 hashes. Three direct calls completed as expected; one raw-link return
faulted; two code-relative returns completed without reaching the expected
continuation. These are historical records, not new runs.

The old kernel log is not available in the current boot log. The task plan
reports an unmapped UL1C read at `0x1000004100`, VM slot `0x22`, for
C2a. This is a secondary account, not a verbatim retained kernel-log block.
The raw failure record itself retains zero firmware timestamps.

The code-relative simulator return model contradicts C2b/C2c and must not be
used as evidence that a new return probe is safe.
