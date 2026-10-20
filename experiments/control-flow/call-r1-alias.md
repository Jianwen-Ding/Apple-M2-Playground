# Call r1 operand/link alias

Question before hardware, 2026-10-20: does `call r1` consume the original r1
operand before writing its implicit return link? The measured simulator now
captures the operand before that write, but alias hardware evidence is absent.

Keep the winner probe's program size, call PC, link, target addresses and
initialized target/mask table fixed. Replace the pre-call sentinel move with
`six-byte mov r1,r30`, then change the two-byte `call r30` to `call r1`.
Each r1 target is a decoded in-program callee. The competing overwritten-link
address is also the valid forward fallthrough continuation, so neither
hypothesis requires an arbitrary target or a loop. Both outcome traces are
bounded. Save the global ID and every trace address before overwriting r1.

The exact aliased program must match its independent host oracle in the
measured simulator before submission. Both uniform-call operand substitutions
use the same r1 target copy and are re-gated. Known-op jump paths, exact before/
after controls, kernel/firmware/memory diagnostics and the shared watchdog are
retained. Start with first-active 0, then 1; stop the batch for any unexpected
semantic result or fault. Failed recovery/blocked host process stops GPU
submissions. Runner: `probe_call_r1.py --first K --winner A|B [--hardware]`.

The initial k=0/1 variants completed through fallback, contradicting the original
consume-before-write simulator hypothesis. A snapshot inserted into existing
fallback stop padding then showed the link in all issue-active r1 values and
original targets in inactive lanes. The exact wait control keeps all original
targets. The next boundary/swap matrix also gates a six-byte known-op surrogate
that writes the link in the issue-active mask and falls through, retaining all
addresses and code size. This tests the observed alias hypothesis as closely
as possible without silently changing the actual call model before recording it.
