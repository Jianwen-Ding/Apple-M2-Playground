# Opcode description runs — 2026-10-11

`scripts/run_drm_opcode_describe.py` on the direct DRM path, `CONFIRM_GPU_FAULTS=1`, only
the 49 non-faulting undecoded opcodes (the runner refuses the 9 faulting ones and 0x6e).
**0 faults** in every run. Raw records (up to 9.3 MB each) stay in
`/scratch/apple-m2-playground/drm-compute/opcode-describe/`. The files here are
summaries from `scripts/analyze_opcode_describe.py`, checked by
`scripts/verify_opcode_describe.py` (`make verify-opcode-describe`, 39 checks).

| File | Contents |
| --- | --- |
| `length-granularity-g64.json` | Main result: 49 opcodes × 8 encodings × 2 layouts plus 102 granularity jobs, 64 register halves declared. All 392 length rows match the oracle exactly. |
| `granularity-bit7.json` | 0x98/0xf8 (0x18/0x78 with bit 7 set) in the granularity variants, alongside `stop` |
| `timing.json` | 37 counted loops (2,000 trips × 64 copies, 8 submissions each): the 31 6-byte no-ops, 0x18, 0x78, `mov_imm`, `wait`, `wait`×3, empty |
| `timing-repeats.json` | Five more runs of a timing subset in separate processes, showing raw loop times varying 2.2× between processes while the ratios hold |
| `length-granularity-g32.json` | Same suite with only 32 halves (r0–r15) declared while r0–r26 were used: 4 corrupted dispatches, exactly the 4 slowest |
| `rerun-g32-anomalies.json` | The 4 corrupted jobs and both references, each rerun 5× with 32 halves: all exact |

Layouts: A = markers right after the candidate; B = one `wait 0` first. A candidate of
length L swallows (ceil((L-2)/4), ceil((L-4)/4)) markers, so (1, 1) means 6 bytes.

## Run log

1. Pilot (refs + 0x18) and the `base` encoding for all 49: the references were exact. This
   is where the 6-byte length of the low-`0b11` class was found, and where 0x6f turned out
   to be in the wrong list (it is decoded by applegpu; the runner's list was corrected).
2. Full suite with 32 halves: 894 jobs, 0 faults, 4 inconsistent dispatches (see `g32` files).
3. Reruns of those 4 (5× each): all exact, so the anomalies were transient. They matched the
   4 slowest dispatches, which led to the register-count check (32 halves = r0–r15 only).
4. Full suite with 64 halves: 894 jobs, 0 faults, 0 inconsistent (3 slow dispatches, all exact).
5. Timing suite, then the bit-7 granularity jobs, then repeated timing runs. The first
   analysis subtracted an empty loop and claimed absolute ns per instruction. A repeat gave
   `mov_imm` at 0.31 ns instead of 2.26 ns, so only raw same-run ratios are claimed now.
