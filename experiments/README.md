# Experiment workspace

Each subject folder starts with questions and dependencies. Once runnable,
give each experiment a stable name such as `timing-001-counter-read` and keep
its source, plan, inputs, and interpretation together. Use
[the experiment template](../templates/experiment.md).

Current subject folders are plans, not successful GPU tests. The first runnable
hardware check is the shared `tests/drm_smoke.c` driver-access test. Promote
confirmed new behavior to `novel-results/` and keep its regression test linked.
