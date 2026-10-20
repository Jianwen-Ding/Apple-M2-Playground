# Ordinary integer-add chain evidence

Eighty-three gzip records preserve exact shader/control bytes, input and full
output tables, instruction boundaries, source/binary/harness hashes, firmware
timestamps, power/boot/memory/kernel snapshots and recovery results. All 249
dispatches complete, all controls and arithmetic outputs are exact, event
counts remain zero, and AC-online stays 1 on the same boot.

`make verify-integer-chain-cost` checks every retained buffer against an
independent scalar sum, regenerates exact program bytes, validates source and
harness provenance, and gates each unique complete program in the simulator.
It predicts the 16 full timing cells from saved shader bytes using the current
dispatch model, with explicit grid/workgroup/register/uniform settings and a
1398 MHz modelling assumption. No hardware is used by the verifier.

`analysis.json` binds all record digests, functional/dispatch binary hashes,
relevant model sources and calibration inputs. It retains every sample,
fast-cluster selection, observed candidate slopes and model residuals. There
are no warnings or unmodelled control paths in these predictions. No timing
parameter was changed. Actual short-dispatch operating frequency is not
established by AC power alone; consecutive-repetition warm-up is a follow-up.

[Interpretation and limits](../../novel-results/2026-10-20-integer-chain-cost/README.md).
