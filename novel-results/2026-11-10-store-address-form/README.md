# In llama.cpp's k_bin_bcast, a device store through a 64-bit register address costs ~3x the same store as uniform base + 32-bit index

Status: confirmed on one device (M2 Max G14C), 2026-11-10. The kernel is our own compile (clang CUDA -> PTX -> ZLUDA ->
AGX) of llama.cpp's `k_bin_bcast<op_add>` (pp512, 512 rows x 896 floats, in place), captured and replayed with
agx_run_hw `--back-to-back 5000`; variants are byte patches of that capture's code, each checked to write the same
output in agx_run. Not reproduced yet by a synthetic probe (see below): the trigger in the kernel is not known.

## Result

| variant (grid 512 x 512 threads, workgroups of 128) | hw us |
|---|---|
| full kernel, store `device_store r8, r24_r25, 0, signed` (as compiled) | 32.8 - 34.3 |
| same, store rewritten to `device_store r8, u4_u5, r26, unsigned` (same addresses) | 22.3 |
| store replaced by `iadd r9, r9, 0` | 17.4 |
| ne0 = 512 (one trip): register form / uniform form / no store | 23.9 / 17.7 / 14.5 |
| ne0 = 512, register form, address pair r28_r29 instead of r24_r25 (r24 is the src0 load's destination), or 64 regs | 23.4 / 23.7 |
| ne0 = 512, store to row 0 only (every row writes the same 2 KB) | 14.8 |

So the stored lines cost ~10 us per MB (~100 GB/s) through the register-address form and ~3 us per MB (the ~365 GB/s
[store floor](../2026-11-01-store-bandwidth/README.md)) through the uniform-base form.

What it is NOT (each changes nothing): data values (src0 / src1 / both zeroed), the buffer object size (dst in its
320 MB capture region or a 1.75 MB one; extra mapped memory), the row layout (synthetic probe with exactly the
kernel's addresses, 896-word rows, 4 workgroups per row), the store's position in the loop, ALU work before the loads
or after the store, in-place vs separate destination.

A synthetic probe (AGX-Performance-Simulator `scripts/probe_hot_lines.py`: 2 loads + wait, fadd, store, with
`REGSTORE=1` = the register form computed by the same `iadd r24_r25, r6_r7, rX_rY, lsl 2`, `ROWW=896 GRID2D=512` =
the kernel's addresses) pays the same small store cost in both forms (10.9 / 11.0 us). What in the real kernel's
register-form store makes it slow is open (its 64-bit index is a sum of two register pairs, r14_r15 + r8_r9,
inside a two-level divergent loop).

## Implications

- Code generators (ZLUDA's AGX backend) may gain by addressing stores as uniform base + 32-bit index where the
  index provably fits: k_bin_bcast 33 -> 22 us per launch.
- AGX Performance Simulator: the store model charges the bytes at 365 GB/s whatever the address form; k_bin_bcast is
  -48% because of this. Not modelled until the trigger is understood.

## Reproducer and evidence

Captures under `/scratch/sim-captures/r5/llama-pp-fa0/*k_bin_bcast*`, patched copies built in
`/scratch/agx-r5/r7/{k1-early,k5-ustore,k1-early-full,k5-full,k6-r28,k7-regs64,k4-row0,ne512-nost,full-nost}`
(the store at code offset 748 moved to 710 and/or replaced). Job scripts and logs:
[evidence](../../results/2026-11-10-store-address-form/).
