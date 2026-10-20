# Overflow reactivation and first-shuffle diagnostics

Twenty-four gzip records preserve the original repeat, instruction-spacing,
destination-seed, width/source, integer-IF, native-form, increment and rotation
diagnostics. Together with [three base programs](../2026-10-20-push-overflow/README.md),
they contain 81 completed dispatches, exact controls, unchanged boot, zero
events, recorded AC-online 0 and established recovery throughout.

`make verify-overflow-first-shuffle` regenerates exact bytes and independently
calculates all counter/payload snapshots, masks, completion words and guards.
The unseeded anomalous low value 0x40 is verified as an observation; it is not
derived as a general architectural rule. Seeded cases independently establish
retention of the chosen low destination half. Every other word is checked.

`model-diagnostic-replay.json` binds 27 record-file digests and simulator
binary/source hashes. It explicitly records **9 full matches and 18 model
counterexamples**, each with its complete list of differing table words.
The payload-without-AND case has two differences; the other failing cases have one. Original failed
classifications and source hashes are preserved through `source-versions`.
No evidence was silently repaired or included in the earlier exact corpus.

The later payload-without-AND record changes word 76 to 0x40 and leaves word
2188 untouched. Both addresses are inside the initialized owned table; this
is a separate addressing/register-visibility discriminator, not a corrected
shuffle-only interpretation. Post-shuffle pop0 fixes the trace, whereas
post-shuffle wait0 does not. A probe with precomputed output indices is next.

[Interpretation, tested workarounds and limits](../../novel-results/2026-10-20-overflow-first-shuffle/README.md).
