# Code fetch and execution overlap only partly: ~max + 0.3 x min of the two

Status: confirmed on one device (M2 Max G14C), our own kernel through ZLUDA's AIR route, back to back.

## Claim

One thread runs straight-line code: 32 segments, each a dependent load to a new line (~300 ns) followed by P FMAs
that use the loaded value. Execution stays ~10 us while the code grows from 16 to 100 64-byte lines (fetch 1.7-10.4 us
at the measured ~104 ns a line, [code fetch](../2026-11-01-code-fetch/README.md)). The command takes (after the 2.3 us
launch) the larger of the two plus 0.27-0.34 of the smaller: with both 10.4 us, 13.3 us, not 10.4 (full overlap) or
20.8 (none).

## Implications

- Code size costs even kernels whose execution is longer than their fetch: ~30% of the fetch time is not hidden.
- AGX Performance Simulator: its fetch rule is now max + 0.3 min (was max); all 56 evaluation captures 9.5 -> 8.2%.

## Reproducer and evidence

`results/2026-11-01-fetch-overlap/fo.ptx` (kernels fo0, fo8, fo24, fo56, fo120); [hardware.txt](../../results/2026-11-01-fetch-overlap/hardware.txt).
