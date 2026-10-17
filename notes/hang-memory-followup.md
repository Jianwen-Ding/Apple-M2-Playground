# Hang evidence and unified-memory follow-up

The owner authorizes higher-risk instruction probes, logging recovered faults
and continuing after a passing recovery control. Persistent unresponsiveness
stops GPU submissions. The owner also requested readiness to investigate
unified-memory triggers if a hang occurs.

`probe_control_followup.py` records the exact code, input buffers, decoded
instruction change, simulator gate, executable simulator hash and harness
source hash before submission. Each phase is saved. It records the kernel-log
delta, complete available stdout/stderr, firmware timestamps, partial readback,
boot identity, event count, AC state, cgroup shmem/current/maximum/events/pressure
and `/proc/meminfo`. The harness stdout includes buffer GPU addresses. On a
10-second host timeout it also reads only its own probe process's status,
wait channel and mappings, sends SIGKILL, and bounds pipe draining to two
seconds. If the process remains blocked, no recovery dispatch is attempted.

On a failure, preserve and push the record and a report identifying the last
completed marker, instruction bytes, affected mappings, fault address if
present, firmware completion state, host process state, memory pressure and
whether the control recovered. Do not infer a GPU hang from missing shader
stores alone: the threadgroup atomic ending-opcode probes complete normally
without continuation stores. Failed-dispatch readback is diagnostic evidence,
not a semantic oracle.

If a control establishes recovery, use the evidence to select one bounded
memory hypothesis at a time:

1. **Address or boundary dependence:** move the initialized test region within
   its allocated buffer, retaining bounds and guard words; compare fault-address
   movement to the instruction's computed address. Never substitute an arbitrary
   address from the kernel log as a new pointer.
2. **CPU/GPU visibility:** compare initialized CPU-written input and GPU-written
   markers across completed dispatch boundaries, using existing visibility tests
   as controls. Keep synchronization changes separate from instruction changes.
3. **Allocation lifetime or pressure:** compare the same small workload in a
   fresh VM/buffer allocation, checking shmem and memory.events before/after.
   Do not deliberately exhaust unified memory to reproduce an unexplained hang.

Each new surrounding program must pass the simulator and its independent
oracle before submission. Change one trigger at a time; retain exact inputs and
full output guards. If the GPU remains unresponsive, limit work to host-side
diagnostics and saving/pushing evidence. A live-hang memory-trigger experiment
has **not** been performed in this follow-up: all 27 variants completed cleanly.
