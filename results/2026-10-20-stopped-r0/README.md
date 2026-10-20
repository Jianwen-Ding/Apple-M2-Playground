# Partial-stop and stopped-source evidence

Nine retained compressed records, each with exact before/after controls.
The initial depth-3 case uses repeated depth payload; eight subsequent cases
use unique lane IDs, maximum depths 1..4, rotations 0/1. Candidate and control
differ only at one STOP/wait instruction. All 27 dispatches completed, zero
faults and exact recovery. Full code/input/readback/hash/diagnostic metadata
and the initial failed storage hypotheses are preserved unchanged.

Tables follow the masked-r0 4,240-word layout: two 32-source counter/payload
gathers, prefix/final markers, inputs and guards. The second gather is after
partial STOP and one pop; final markers follow four more pops. Source lanes
that have stopped yield the surviving writer's own value. Masked live sources
remain readable. The simulator mismatch is preserved as a source-liveness
gap, without claiming a stopped lane's underlying counter storage is read.

`source-before-model/` retains exact initial builder versions. Run
`make verify-stopped-r0` to resolve hashes, reconstruct code, check the one-word
STOP/wait difference and independently check every readback word. See the
[finding](../../novel-results/2026-10-20-stopped-r0/README.md).
