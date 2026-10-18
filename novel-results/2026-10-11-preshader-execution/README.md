# Preshader (preamble) execution model on G14C

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute.

## Claim and scope

* **The preamble runs exactly once per core per dispatch**, only on cores that
  receive work, regardless of workgroups per core (1–60). Shown with an atomic
  per-core counter.
* It runs with **one active lane** (SR57 = SR59 = 1), in **SIMD-group slot 96**
  (SR17), with SR0 = 0 and **SR24 = 5** (the main compute shader reads 2).
* **Uniforms it writes are per core:** every main-shader lane sees the copy written
  by the preamble on its own core (SR20 pairing, 66,112 lanes).
* A device `atomic add` without return value (`1500208e10500400` form:
  [u8_u9 + r1] += r2) counts exactly (65,536 contending lanes).

Update 2026-10-18: it runs once per core per dispatch also for several commands per submit, and the uniform file, register and cost
questions are answered in the [follow-ups](../2026-10-18-preshader/README.md).

Not established: whether the preamble can be re-run within a dispatch, and fragment preambles.

## Reproducer and evidence

`make sr-direct` (includes preamble and atomic configs), `make verify-sr-direct`
(checks 9–12). [Report](../../experiments/registers/sr-direct-drm.md) ·
[evidence](../../results/2026-10-11-sr-direct-drm/README.md).

## Relationship to existing knowledge

Mesa compiles uniform setup into a "preamble" run before the main shader and
relies on its results being visible to all invocations, without stating its
execution granularity. applegpu describes `atomic` and `uniform_store` encodings
but has no hardware test of them on Asahi. The run count, single-lane context,
slot 96 and SR24 code were measured here.

## Compiler implications and limitations

For a CUDA backend the preamble is a once-per-core hook. It suits hoisting
dispatch-uniform computation (address bases, constants) out of every thread at
negligible cost: one lane, once per core. It must not hold per-workgroup state,
because uniforms are shared by every workgroup on that core. Device atomics (add,
no return) are available for global counters.
