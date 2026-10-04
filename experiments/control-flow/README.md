# Control-flow and lane probes

Questions: lane identifiers, execution masks, divergence/reconvergence,
conditional branches, shuffle behavior, and barrier scope.

First case: write an independently known value for every launched lane, then
add one bounded branch and compare the output mask. Record launch dimensions
and active lanes rather than assuming a SIMD width from another generation.

Requires stable submission and deterministic per-lane readback. Use bounded
loops and an execution timeout in the eventual runner.
