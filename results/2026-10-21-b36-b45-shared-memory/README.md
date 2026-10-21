# B36 and B45: sharing GPU memory across processes and between VMs (2026-10-21)

Blockers B36 and B45 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM through
agx_runtime plus a local PRIME patch (`agx_runtime-dmabuf.patch`: `Bo::export_dmabuf`, `Vm::import_dmabuf`; ZLUDA is not
pushed). Battery power, 3 runs, identical results, 0 faults; hang budget unchanged.

## B36: dma-buf IPC works; there is no user-pointer import

**Result: a buffer object exported with `DRM_IOCTL_PRIME_HANDLE_TO_FD` and imported in another process with
`PRIME_FD_TO_HANDLE` binds in that process's VM like any other object, and both GPUs' accesses are coherent with each
other and with both CPU mappings once the commands have completed.**

`b36_ipc.rs`: process P runs `writer.bin` (4,096 lanes store 0x10186a00 at S[8 + gid] after a ~8 ms loop), exports S,
forks; the child opens its own render-node fd and VM, imports S at its own address (0x1100400000), runs `reader.bin`
(out[8 + g] = S[g]) and then `count.bin` (S[8 + g] = g):

| Check | Result |
| --- | --- |
| child's CPU mapping of the imported object | 4,096 / 4,096 words written by P's GPU |
| child's GPU read of the imported object | 4,088 / 4,088 |
| P's CPU mapping after the child's GPU writes | 4,096 / 4,096 |

Binding an imported object needs nothing special: the usual `VM_BIND` (read / write) at any free address, the mmap
offset from `GEM_MMAP_OFFSET`, and no `DRM_ASAHI_GEM_VM_PRIVATE` on the exporter's object (VM-private objects refuse
export by design). So `cuIpcGetMemHandle` / `cuIpcOpenMemHandle` can be built on dma-buf fds (passed over a Unix
socket with `SCM_RIGHTS`, or by `pidfd_getfd`).

**No user-pointer import:** the Asahi UAPI has 11 ioctls (GET_PARAMS, GET_TIME, VM_CREATE / DESTROY, VM_BIND,
GEM_CREATE, GEM_MMAP_OFFSET, GEM_BIND_OBJECT, QUEUE_CREATE / DESTROY, SUBMIT) and none takes a CPU pointer, and this
kernel has no `/dev/udmabuf` to turn memfd-backed host memory into a dma-buf. `cuMemHostRegister` of arbitrary existing
memory cannot be zero-copy; ZLUDA has to allocate GPU memory and copy (or, for `cudaHostAlloc`, hand out GPU objects
mapped on the CPU, which it already does).

## B45: ordering between VMs that share an object

The same object S bound in two VMs of one fd (VM 1 and VM 2), VM A running `writer.bin` into S, VM B `reader.bin` from S:

| VM B's command | B saw A's writes | Timing (us from A's start) |
| --- | --- | --- |
| after a host wait for A's fence | 4,088 / 4,088 | A ends 7,805; B 8,224-8,230 |
| submitted at once with A's timeline point as a wait (`submit_compute(.., &[a_fence])`) | **4,088 / 4,088** | A ends 8,273; B 8,404-8,410 |
| submitted at once, no wait | **0 / 4,088** | B ran at 124-131 us, concurrently with A |

**Rule: nothing orders commands of different VMs (or different queues) implicitly; they run concurrently (as B43
shows). A syncobj wait on the producer's point is enough for full visibility** (no extra cache flush, no host
round-trip); it costs ~130 us of hand-over between A's end and B's start, against ~420 us for a host wait. ZLUDA must
translate cross-context dependencies (events, `cudaStreamWaitEvent` across contexts, IPC handles plus events) into
syncobj waits; the simulator's multi-context mode should give no implicit ordering between VMs.
