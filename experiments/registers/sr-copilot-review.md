# Special-register scan review

Offline review of `scripts/patch_agx_sr.py`,
`scripts/run_agx_sr_scan.py`, and
`/scratch/apple-m2-playground/sr-scan-runs/20261004T233344915565Z/record.json`.
No new GPU execution was performed. The record is authoritative for this
review: it reports `passed=true`, `complete=true`, all 256 selectors, three
repeats, and 257 lanes.

## Findings

- **Selector packing is verified, not assumed.** The instruction word uses
  `SR[5:0]` at bits 16..21 and `SR[7:6]` at bits 26..27. For every patched
  selector the decoder checked `MovFromSrInstructionDesc`, four-byte size, and
  exact `{'Dt': 2, 'D': 4, 'SR': selector}` fields. The archived evidence
  includes, for example, selector 255 decoding as `get_sr r2, sr255`.
- **The pinned replacement is data-only.** The six-byte site changes from
  `620978563412` (the pinned-constant `mov6`) to the four-byte `get_sr`
  followed by two-byte `wait 0`; all non-wrapper mutations are confined to
  that site. The unchanged control returned `0x12345678` before and after the
  scan, and all 18 control checkpoints passed.
- **Readback protection is adequate for the executed path.** The Vulkan event
  checks require successful shader creation, submit, and fence wait. The
  readback length is exact; the eight-word prefix, inactive words, 16-word
  tail guard, and known selector oracles are checked. Selectors 0, 4, 5, 6,
  48, 51, 52, 53, and 80 matched their expected lane/group values on every
  repeat. There were zero failures.
- **Current paired-read metadata is corrected.** The current `patch_pair`
  rejects an original metadata value other than 70 and writes
  `main_size = len(main) + 16`. The 16 bytes are the original post-`stop`
  instruction-fetch padding; using 54 would be a real metadata defect.
  The archived 23:33:44Z scan predates `patch_pair`, so it does not validate
  paired reads or clock separation.

## Data observations and limits

Most selectors 1..255 returned zero, but “zero” is only an observation under
this shader/state, not proof that a register is nonexistent. Several selectors
outside the `KNOWN` oracle set returned stable nonzero or lane-varying values:
7, 8, 9, 10, 15, 16, 19, 24, 25, 32, 56, 57, 58, 59, 60, 63, 97, and 114.
These are useful candidates for follow-up, but the scan does not establish
their names or semantics. Selector 21 varied across repeats (lane-zero values
50, 51, 52), and selector 113 produced 8 once then 0, so both are
stateful/unstable observations rather than reliable register identities.

This scan provides no clock inference. It has no timestamp or cycle oracle,
does not compare two reads separated by a controlled instruction interval,
and does not establish that any unnamed selector is a timer. In particular,
the selector-21/113 variation is insufficient to call either a clock. The
coordinator’s paired-read experiment, with a corrected `main_size` of 70 for
the original layout, is the appropriate next evidence, but remains outside
this archived record.

## Paired-read follow-up

The paired record
`/scratch/apple-m2-playground/sr-scan-runs/20261004T233933832022Z/record.json`
passed with all 256 selectors, three repeats, 16 lanes, and gap 128. The
offline verifier in `scripts/verify_sr_evidence.py` reconstructs each output
shader from the embedded baseline and `main_hex`, checks refreshed wrapper
SHA-1 and recorded SHA-256 values, validates metadata/code offsets, selector
split bits, all readback guards/padding/tails, event completion, counts, and
known oracles. It does not read child readback files or execute a GPU.

| Observation | Result |
|---|---|
| First-versus-second read delta | `0` for every lane of all 256 selectors; no within-dispatch ticking candidate |
| SR21 | paired values equal in every repeat; lane-zero first values `2, 6, 9` across the three repeats |
| SR113 | paired values `0, 0` in all lanes and repeats |
| Other repeat changes | none observed at lane zero |

Thus SR21 shows dispatch-to-dispatch state variation but no gap-128 read
variation; SR113 supplies no ticking signal. Neither supports a clock
identification. The verifier accepts a record path (or a JSON object wrapped
under `record`) and exits status 1 for malformed, incomplete, digest-invalid,
guard-corrupted, or oracle-invalid evidence; `--selftest` exercises corrupted
readback rejection.

## Verifier strengthening and context repeat

`verify_sr_evidence.py` now has strict full-scan validation by default and
`--partial` mode for bounded counts 1..257, repeats 2..5, and requested
subsets. It requires unique observed/requested selectors, matching parent
patch selectors, reconstructed shader SHA-256 equality, positive ordered host
brackets, the expected Apple M2 Max/Honeykrisp/Mesa identity and UUID, and
zero-result status for every API event. It also checks original/paired control
hashes, all three pair deltas, and self-test rejection of refreshed-hash guard
tampering, missing samples, duplicate selectors, and wrong shader hashes.
All 15 count characterization records (`count-{1..257}` subset) pass
`--partial`; the prior full simple and paired records and clean self-tests
also pass.

The new sparse-even path is covered offline in the verifier using the recorded
`7e0942128000` parity-AND and `520844020000` conditional bytes, rebuilt main
metadata, and sentinel checks for every odd payload lane. No sparse-even
record was present at review time.

The repeated same-context record
`/scratch/apple-m2-playground/sr-context-runs/20261004T234523094206Z/record.json`
contains 12 dispatches per child with 10 ms spacing. SR21 stayed at 47 across
all dispatches; SR113 was 0 for 11 dispatches and 8 on the last. SR32 decreased
by `0x24000` each new command buffer. That monotonic change is consistent with
an allocation/address-related hypothesis, not a clock: it is command-buffer
granularity, lacks a cycle oracle, and is not evidence of elapsed time.
The read-only `vulkan_sr_repeated.c` harness reinforces this limitation: it
allocates and submits a fresh command buffer/fence for each iteration, so
cross-iteration values cannot be interpreted as an in-shader timer without
separate timing controls.

## Coordinator integration verification

After these Copilot reviews, the coordinator checked the completed sparse-even
record and the smaller same-context records. Integration corrected sparse-control
reconstruction, aggregation of pair deltas across every repeat, and guard mutation
in the corruption self-test. `make verify-sr` verifies all retained successful
records: 2,522 readbacks and 435,904 uint32 words. These integration checks were
performed by the coordinator; they are separate from Copilot's historical reviews.
