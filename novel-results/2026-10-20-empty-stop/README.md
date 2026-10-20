# Stop behavior depends on participation and return context

**Later direct-read correction:** [return-arrival snapshots](../2026-10-20-ret-mask-state/README.md) show the previously inactive depth-1 lanes already active with r0l=0 before any pop. The shallow post-return stop below is therefore not empty on hardware. The observations remain valid; the old interpretation of their incoming state is superseded.

Observed on the project's M2 Max G14C B1, direct DRM, compute, AC power,
2026-10-20. **17 variants, 51 dispatches including exact before/after controls,
zero faults, all recovery controls passed.** The new probes expose six exact
counterexamples to the current functional simulator; its existing rule remains
unchanged pending a model of the additional state.

The [2026-10-17 return model](../2026-10-17-call-ret/README.md) treated an
empty-mask `stop` as killing depth-1 lanes whenever other lanes had depth >=2.
Isolating the instruction from return shows that this is **not a general rule**.
All probes prepare their addressing before masking, use complete programs and
one full 32-lane group, and contain no data-dependent loops or barriers.

## Three distinct observations

1. **Empty masks built with conditionals: stop behaves like wait.** Build
   effective mask depths with `if_icmp` and `push_exec`, issue `stop`, then
   checkpoint after each of three `pop_exec ..., 1` operations. Depths 1,2,3
   uniformly and mixtures 1/2, 1/3 and 2/3 all reactivate at the expected pop.
   Depth-1 lanes survive even alongside depth-2/3 lanes. The current simulator
   incorrectly suppresses them in mixtures 1/2 and 1/3.
2. **Partially active stop: only the issuing lanes disappear.** Odd lanes
   active, even lanes masked at effective depth 1. After `stop`, even lanes
   resume after the next pop and execute every remaining checkpoint and final
   store; odd lanes never write again. This repeats exactly. The simulator
   instead ends the entire SIMD group as soon as it sees any active lane.
3. **A preceding return changes the empty-stop outcome.** Odd lanes execute
   a uniform `ret r31` to an in-program instruction boundary. Without a stop
   at the target, even lanes write after pop 1 and all lanes write after pop 2.
   Inserting 1,2,8 or 32 stops **before the first pop** suppresses the even
   lanes at every checkpoint; odd lanes resume after pop 2. Zero-stop and
   one-stop cases repeat exactly. These return-context cases match the old
   simulator hypothesis; the same reactivation pattern made with conditionals
   does not.

| Context at test instruction | Pop 1 marker | Pop 2 marker | Pop 3 marker |
| --- | --- | --- | --- |
| Conditional 1/2 mixture; stop or wait | depth-1 lanes | all | all |
| Conditional 1/3 mixture; stop or wait | depth-1 lanes | depth-1 lanes | all |
| Conditional 2/3 mixture; stop or wait | none | depth-2 lanes | all |
| Odd lanes active at stop, even lanes masked | even | even | even |
| Partial return, no intervening stop | even | all | all |
| Same return, 1/2/8/32 stops at landing | none | odd | odd |

“Depth” here describes the independently constructed mask state and its pop
reactivation pattern. The probe does not read the hardware's complete mask or
return state before `stop`. The final visible r0l snapshots are zero in lanes
that reach the last checkpoint. These observations establish that the simple
software depth abstraction is insufficient; they do not identify the hidden
state, the hardware dead-lane representation, or a universal stop formula.

## Validation and implications

The exact programs first pass a scalar-oracle simulator gate under
`AGX_EXPERIMENTAL_RET=buffer-pop2`. For previously unmeasured behavior this
validates the hypothesis and bounded surrounding code. The retained hardware
bytes then decide it. The report deliberately preserves the simulator's
incorrect predictions alongside the hardware counterexamples.

Return targets are buffer-relative, inside fully decoded programs. A known-op
surrogate constructs the return-arrival mask using conditionals and reaches
the landing with `jmp_exec_none`; its stop region uses waits. Every trace,
main-output word, guard and untouched tail must match its independent oracle.
That no-return program is also the known-good recovery control.

A PTX backend must preserve early lane exits rather than assume that every
`stop` ends the entire group. It also cannot apply the return-specific
empty-stop heuristic to ordinary conditional masking. Inline device functions
until a measured model covers the intended return scope.

The watchdog records kernel deltas, firmware completion, exact code and inputs,
process metadata on timeout, boot/budget, AC and memory snapshots. No timeout
or fault occurred here. The immediate post-child shmem snapshot is 1,769,472 B;
it is zero again at each next probe, with unchanged memory.events. This is
asynchronous release, not evidence of a persistent leak.

```sh
python3 -B scripts/probe_empty_stop.py mix12                 # simulator hypothesis
python3 -B scripts/probe_empty_stop.py mix12 --hardware      # controls + variant
python3 -B scripts/probe_ret_stop_context.py --stops 1       # both surrogate and actual-model gate
python3 -B scripts/probe_ret_stop_context.py --stops 1 --hardware
make verify-empty-stop                                     # no GPU
```

Records refuse overwrite; use `--repeat N` for another hardware repetition.
[Evidence and layout](../../results/2026-10-20-empty-stop/README.md).
Open: exact return-state mechanism, mask polarity/shape, partial-stop behavior
at more depths, and a qualified simulator model that preserves existing returns.
