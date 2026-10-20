# Arithmetic core-placement evidence

Twenty-eight gzip records preserve exact shader/control bytes, inputs and
complete final buffers, arithmetic and tag planes, guards, actual native delay
configuration, every repetition/wait/completion marker and firmware/get-time
timestamp, launch/source/binary hashes, kernel/memory/power snapshots and
recovery controls. There are 1552 candidate submits and 56 controls, with
zero faults. Intermediate candidate buffers are not captured.

`make verify-integer-core-distribution` performs no GPU work. It rebuilds each
unique complete program, checks literal default-placement simulation against
independent arithmetic/tag expectations, and checks successive table states.
The hardware checker independently validates every arithmetic/guard word,
literal SR19 tags, and every SR20 tag's enabled-core mask and workgroup
uniformity. It recomputes each full per-core and per-cluster histogram. A
partial core subset is retained as a possible finding, not rejected by the
oracle; all 12 full-size SR20 maps happen to contain all 38 cores.

The verifier checks actual delay, device parameters, all repetitions and
timestamp brackets, minimum measured host intervals and nonoverlapping whole
probe windows. `analysis.json` binds records, current and archived builders,
native/functional/model binaries, sources and calibration inputs. The recorded
builder is archived before hardening the missing-readback error path; shader
bytes and the hardware data are unchanged.

`prechange-defaults.json` retains eight model outputs from before adding the
explicit measured-peak input. The verifier requires the current default output
to match each object exactly. It also checks invalid CLI peak counts fail
before a nonexistent shader can be opened. For every full-size SR20 record,
it predicts with the measured cumulative peak and retains that sensitivity
beside the matching final-dispatch duration and complete core map.

`make test-integer-core-distribution` checks histogram counts against a small
independent fixture and injects arithmetic, output/table-guard, disabled-core,
split-workgroup, missing-word, allocation-tag and missing-readback defects.
The simulator's three `observed_peak` unit tests check input limits, partial
waves, launch work, distinct representative workgroups and the unchanged
default-count result. No GPU is accessed by those tests.

[Interpretation and limits](../../novel-results/2026-10-20-integer-core-distribution/README.md).
